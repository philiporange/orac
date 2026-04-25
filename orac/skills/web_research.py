"""
Web research skill using Gemini's URL context and Google Search tools.

Uses the google-genai SDK to have Gemini read a URL directly and search
the web for additional context. This is particularly useful for researching
companies from their website to extract values, culture, and other signals
for job application tailoring.
"""

import os
from typing import Any, Dict, Union

from google import genai
from google.genai.types import GenerateContentConfig


def execute(inputs: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
    """
    Research a URL using Gemini's URL context and Google Search tools.

    Args:
        inputs: Dictionary containing:
            - url (str): The URL to research
            - prompt (str): Instructions for what to extract
            - model (str, optional): Gemini model to use

    Returns:
        Dictionary containing:
            - result (str): The research output text
            - urls_retrieved (list): URLs that Gemini successfully fetched
    """
    url = inputs["url"]
    prompt = inputs["prompt"]
    model = inputs.get("model", "gemini-2.5-flash")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY environment variable is required for web research"
        )

    client = genai.Client(api_key=api_key)

    full_prompt = f"{prompt}\n\nPrimary source URL: {url}"

    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=GenerateContentConfig(
            tools=[{"url_context": {}}, {"google_search": {}}],
            temperature=0.3,
        ),
    )

    # Extract URLs that were retrieved
    urls_retrieved = []
    for candidate in response.candidates:
        meta = getattr(candidate, "url_context_metadata", None)
        if meta and hasattr(meta, "url_metadata"):
            for url_meta in meta.url_metadata:
                status = getattr(url_meta, "url_retrieval_status", "")
                if "SUCCESS" in str(status):
                    urls_retrieved.append(
                        getattr(url_meta, "retrieved_url", "")
                    )

    return {
        "result": response.text,
        "urls_retrieved": urls_retrieved,
    }
