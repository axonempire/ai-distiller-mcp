import sys
import shutil
from typing import List

from pydantic import BaseModel, Field
import typer
import dspy

from pathlib import Path
from mcp.server.fastmcp import FastMCP
from loguru import logger
import mcp.types as types

from server.gmail import GmailAPIClient, emails_to_json
from server.utils import ensure_datetime

# Initialize server
mcp = FastMCP("ai-news-distiller-mcp")

# dspy
lm = dspy.LM("anthropic/claude-3-5-haiku-20241022")

@mcp.tool()
def say_smth_stupid() -> list[str]:
    """Returns a stupid message."""
    return lm("Say something stupid", temperature=1.0)


logger.info("Initializing Gmail client. Current directory: {os.getcwd()}")
gmail_client = GmailAPIClient(credentials_file="credentials.json")
                
class Email(BaseModel):
    title: str = Field(description="Email title")
    sender: str = Field(description="Email sender")
    date: str = Field(description="Email date in YYYY-MM-DD HH:MM:SSformat")
    content: str = Field(description="Email content")

class ReviewEmails(dspy.Signature):
    """Review the emails passed and select the ones that are interesting for the topic at hand"""
    emails: List[str] = dspy.InputField(description="List of emails to review")
    topic: str = dspy.InputField(description="Topic to review the emails for")
    period: str = dspy.InputField(description="Period to review the emails for")
    # Output
    selected_emails: List[Email] = dspy.OutputField(description="List of emails that are interesting for the topic at hand")


class Distiller(dspy.Module):
    def __init__(self):
        super().__init__()
        self.review_emails = dspy.ChainOfThought(ReviewEmails)
    
    def forward(self, emails: List[str], topic: str, period: str) -> str:
        logger.info(f"Calling review_emails with {emails}, {topic}, {period}")
        result = self.review_emails(emails=emails, topic=topic, period=period)
        logger.info("--------------------------------")
        logger.info(type(result))
        logger.info(result)
        logger.info("--------------------------------")
        
        selected_emails_content = result.selected_emails
        
        logger.info(f"News digest type: {type(selected_emails_content)}")
        logger.info(f"News digest content: {selected_emails_content}")
        
        string_emails = [email.model_dump_json(indent=2) for email in selected_emails_content]
        
        return " ".join(string_emails)

@mcp.tool()
def distill_news(emails: List[str], topic: str = "AI news", period: str = "current week") -> str:
    """Retrieve the list of emails from the period specified and filter only those that are relevant to the topic"""
    distiller = Distiller()
    result = distiller(emails=emails, topic=topic, period=period)
    return result


@mcp.tool()
def get_user_profile() -> str:
    """Get the user profile from the Gmail client"""
    profile = gmail_client.get_user_profile()
    if profile:
        return f"👤 Authenticated as: {profile.get('email')}\n📧 Total messages in account: {profile.get('messages_total', 'Unknown')}"
    else:
        return "❌ Error getting profile"


@mcp.tool()
def get_emails(start_date: str = "yesterday", end_date: str = "today", max_emails: int = 10) -> str:
    """Get the emails from the period specified. If no period is specified, get the emails from the current day."""
    start_datetime = ensure_datetime(start_date)
    end_datetime = ensure_datetime(end_date)
    emails = gmail_client.get_emails_by_date_range(start_datetime, end_datetime, basic_data=True, max_results=max_emails)
    return emails_to_json(emails)

# Old stuff. Keeping it here just for reference.

# @mcp.tool()
# def distill_ai_news_instructions(period: str = "current month", number_of_news_items: int = 50) -> str:
#     """Returns instructions to distill AI news and events."""
#     return ai_news_distiller(period, number_of_news_items)


# @mcp.prompt()
# def ai_news_distiller(period: str = "current month", number_of_news_items: int = 50) -> str:
#     prompt = f"""Review {period} Gmail emails and identify senders corresponding to AI-related newsletters. For each identified newsletter, read all issues from the past month. From these, compile a digest of at least {number_of_news_items} notable AI news items. For each news item:
#         - Include a one-line summary as a headline.
#         - Add the publication date.
#         - Provide a brief, clear technical summary for a knowledgeable audience.
#         - Insert a clickable source link.
#         - Assign an importance rating from 1 (minor) to 5 (high impact).
#         - Organize the news chronologically or by theme for readability.
#     At the end, include a separate section listing AI-related events happening in San Francisco during the current month, with event names, dates, venues, and source links.
#     Ensure the digest is concise, technically accurate, and accessible to expert readers, while preserving essential details and trends.
#     To distill the news, use only the information provided in the emails. Do an exhaustive search in the emails retrieving all the information available to satisfy the request requirements.
#     """
#     return prompt


def main(debug: bool = False):
    dspy.configure(lm=lm)

    try:
        logger.info("Starting AI News Distiller MCP Server...")
        mcp.run()
    except KeyboardInterrupt:
        logger.warning("Ctrl+C caught! Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Exception {e}")
        sys.exit(1)


if __name__ == "__main__":
    typer.run(main)
