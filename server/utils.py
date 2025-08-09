from datetime import datetime, timedelta

from loguru import logger


def ensure_datetime(date_string: str) -> datetime:
    """Parse date string in various formats and return a datetime object."""
    
    match date_string:
        case "today":
            return datetime.now()
        case "yesterday":
            return datetime.now() - timedelta(days=1)
        case "last_week":
            return datetime.now() - timedelta(days=7)
        case "last_month":
            return datetime.now() - timedelta(days=30)
        case "last_year":
            return datetime.now() - timedelta(days=365)
        case _:
            logger.info(f"Parsing date: {date_string}")            
            formats = [
                '%Y-%m-%d',
                '%m/%d/%Y',
                '%d/%m/%Y',
                '%Y-%m-%d %H:%M:%S',
                '%m/%d/%Y %H:%M:%S'
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_string, fmt)
                except ValueError:
                    continue
            
            raise ValueError(f"Unable to parse date: {date_string}")
