import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from devtools import debug
from github import Github
from github.NamedUser import NamedUser
from pydantic import BaseSettings, SecretStr
from pydantic.main import BaseModel

from app.model import Organization, PullRequest, Repository


class Settings(BaseSettings):
    github_repository: str
    input_token: SecretStr
    github_event_path: Path
    github_event_name: Optional[str] = None
    input_latest_changes_file: Path = Path("README.md")
    input_latest_changes_header: str = "### Latest Changes\n\n"


class GitHubEventPullRequest(BaseModel):
    action: str
    number: int
    changes: Optional[dict] = None
    pull_request: PullRequest
    repository: Repository
    organization: Optional[Organization] = None
    installation: Optional[dict] = None
    sender: Optional[dict] = None


logging.basicConfig(level=logging.INFO)
settings = Settings()
logging.info(f"Using config: {settings.json()}")
# g = Github(settings.input_token.get_secret_value())
# repo = g.get_repo(settings.github_repository)
# owner: NamedUser = repo.owner
# github_event: Optional[GitHubEventPullRequest] = None
if settings.github_event_path.is_file():
    contents = settings.github_event_path.read_text()
    github_event = GitHubEventPullRequest.parse_raw(contents)
    debug(github_event)
    logging.info(github_event.json(indent=2))
    if not github_event.pull_request.merged:
        logging.error(
            "The PR was not merged but this action was run, add a step to your GitHub Action with:"
        )
        logging.error("if: github.event.pull_request.merged == true")
        sys.exit(1)
    if not settings.input_latest_changes_file.is_file():
        logging.error(
            f"The latest changes files doesn't seem to exist: {settings.input_latest_changes_file}"
        )
        sys.exit(1)
    logging.info("Setting up GitHub Actions git user")
    subprocess.run(["git", "config", "user.name", "github-actions"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "github-actions@github.com"], check=True
    )
    logging.info(f"Pulling the latest changes, including the latest merged PR (this one)")
    subprocess.run(["git", "pull"], check=True)
    content = settings.input_latest_changes_file.read_text()
    match = re.search(settings.input_latest_changes_header, content)
    if not match:
        logging.error(
            f"The latest changes file at: {settings.input_latest_changes_file} doesn't seem to contain the header RegEx: {settings.input_latest_changes_header}"
        )
        sys.exit(1)
    pre_content = content[: match.end()]
    post_content = content[match.end() :]
    message = f"* {github_event.pull_request.title}. PR [#{github_event.pull_request.number}]({github_event.pull_request.html_url}) by [@{github_event.pull_request.user.login}]({github_event.pull_request.user.html_url}).\n"
    new_content = pre_content + message + post_content
    settings.input_latest_changes_file.write_text(new_content)
    logging.info(f"Committing changes to: {settings.input_latest_changes_file}")
    subprocess.run(["git", "add", str(settings.input_latest_changes_file)], check=True)
    subprocess.run(["git", "commit", "-m", "📝 Update release notes"], check=True)
    logging.info(f"Pushing changes: {settings.input_latest_changes_file}")
    subprocess.run(["git", "push"], check=True)
logging.info("Finished")
