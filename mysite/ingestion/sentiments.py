# ingestion/sentiments.py

def news_analysis(headline: str) -> str:
    """
    Retorna APENAS: 'Positive', 'Neutral' ou 'Negative' para o headline.
    """
    import os
    from pathlib import Path
    from dotenv import load_dotenv
    from cerebras.cloud.sdk import Cerebras

    if not headline or not headline.strip():
        return "Neutral"

    # carrega .env ao lado do manage.py (independente do cwd)
    BASE_DIR = Path(__file__).resolve().parents[1]
    load_dotenv(BASE_DIR / ".env")

    cb = Cerebras(api_key=os.getenv("CEREBRAS_API_KEY"))
    resp = cb.chat.completions.create(
        model="gpt-oss-120b",
        messages=[
            {"role": "system", "content": "Reply with exactly ONE word: Positive, Neutral, or Negative."},
            {"role": "user", "content": headline.strip()},
        ],
        stream=False,
        max_completion_tokens=100,  # folga pra evitar finish_reason='length'
        temperature=0,
        top_p=1,
    )

    # extrai o texto onde quer que venha
    text = None
    try:
        msg = resp.choices[0].message
        text = msg.content if msg.content is not None else msg.reasoning
    except Exception:
        pass
    if not text:
        text = getattr(resp.choices[0], "text", None) or getattr(resp, "output_text", None)
    if not text:
        try:
            d = resp.model_dump()
            ch0 = (d.get("choices") or [{}])[0]
            m = (ch0.get("message") or {})
            text = m.get("content") or m.get("reasoning") or ch0.get("text")
        except Exception:
            return "Neutral"

    label = (str(text).strip().split()[0]).strip(",. ").title()
    if label == "Good":  # normaliza se o modelo usar 'Good'
        label = "Positive"
    return label if label in {"Positive", "Neutral", "Negative"} else "Neutral"
