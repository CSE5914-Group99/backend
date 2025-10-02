from dotenv import load_dotenv

load_dotenv()

from langchain_tavily import TavilySearch

# Langchain tool directly, just need the tavily key
basic_tavily_search = TavilySearch(
    max_results=3,
    topic="general",
    include_answer=True,
    # include_raw_content=False,
    # include_images=False,
    # include_image_descriptions=False,
    # search_depth="basic",
    # time_range="day",
    # include_domains=None,
    # exclude_domains=None
)

if __name__ == "__main__":
    # Basic query example
    print(basic_tavily_search.invoke({"query": "Who should i bet on in the nba finals this year"}))