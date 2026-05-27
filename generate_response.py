import os
import ollama
import logging
import tiktoken
from sambanova import SambaNova

from scraper import clean_markdown

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv('API_KEY')

logger = logging.getLogger(__name__)

_client = None

def get_sambanova_client():
    global _client
    if _client is None:
        _client = SambaNova(
            api_key=API_KEY,
            base_url="https://api.sambanova.ai/v1",
        )
    return _client

def format_time(response_time):
    minutes = response_time // 60
    seconds = response_time % 60
    return f"{int(minutes)}m {int(seconds)}s" if minutes else f"Time: {int(seconds)}s"


def trim_to_token_limit(text, model, max_tokens=40000):
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(text)
    if len(tokens) > max_tokens:
        trimmed_text = encoder.decode(tokens[:max_tokens])
        return trimmed_text
    return text


def get_prompt(query, scraped_data) :
    prompt = f"""You are a data extraction engine. Extract information from the Scraped Data below into CSV format.

### Scraped Data:
'''
{scraped_data}
'''

### Fields to extract:
"{query}"

### Rules (STRICT):
1. Output ONLY valid CSV. No explanation, no markdown, no code blocks.
2. First line = header row with column names matching the requested fields.
3. Every data row MUST have the SAME number of columns as the header.
4. Each column must contain ONLY its own data — never merge multiple fields into one column.
5. If a value contains a comma, wrap the entire value in double quotes.
6. If a value contains a double quote, escape it as "".
7. Do NOT leave any column empty if the data exists in the source.
8. Extract ALL matching items from the page, not just a few.

### Example (for fields: quote, author):
quote,author
"The world is a book, and those who do not travel read only one page.",Saint Augustine
Life is short. Smile while you still have teeth.,Unknown

### CSV Output:
"""

    print('prompt : ', prompt[:200], '...')
    return prompt

# - If the required information is missing, output: "The provided context does not contain enough information."  

def generate_response(ollama_model, query, scraped_data):
    """Generates a response using scraped data and an LLM."""

    logger.info(f"Generate Response from Ollama LLM: {ollama_model}")

    prompt = get_prompt(query, scraped_data)

    try:
      response = ollama.chat(
        model=ollama_model,
        messages=[{"role": "user", "content": prompt}],
        options={"num_predict": 8192}
      )
      return response.get("message", {}).get("content", "")
    except Exception as e:
      logger.error(f"Ollama error: {e}")
      raise RuntimeError(f"Failed to generate response using Ollama: {e}")


def generate_response2(query, scraped_data, llm_name='QwQ-32B', retry=2):

    logger.info(f"Generate Response from Sambanova LLM: {llm_name}")

    if not API_KEY or API_KEY == "placeholder":
        raise RuntimeError("Sambanova API_KEY not configured. Set it in .env file.")

    prompt = get_prompt(query, scraped_data)
    client = get_sambanova_client()

    response = client.chat.completions.create(
        model=llm_name,
        messages=[
          {
            "role": "user",
            "content": prompt
          }
        ],
        temperature=0.1,
        top_p=0.1,
        timeout=120
    )

    # print(f'Response: {response}')

    if hasattr(response, "error"):
      error_message = response.error.get("message", "Unknown error")
      logger.error(f"Sambanova API error: {error_message}")

      if "maximum context length" in error_message.lower() and retry != 0:
        logger.warning("Token limit exceeded, retrying with reduced content...")

        if retry == 2:
          cleaned_scraped_data = clean_markdown(scraped_data, remove_links=True)
          return generate_response2(query, cleaned_scraped_data, llm_name, retry=1)

        elif retry == 1:
          cleaned_scraped_data = trim_to_token_limit(scraped_data, "gpt-4o", max_tokens=35000)
          return generate_response2(query, cleaned_scraped_data, llm_name, retry=0)

      raise RuntimeError(f"API Error: {error_message}")

    return response.choices[0].message.content