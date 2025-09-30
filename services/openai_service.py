import openai
from config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY

def generar_texto_openai(prompt: str, model: str = "gpt-4o-mini", max_tokens: int = 1500) -> str:
    response = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    return response['choices'][0]['message']['content'].strip()

def generar_embedding(texto: str):
    response = openai.Embedding.create(
        model="text-embedding-ada-002",
        input=texto
    )
    return response['data'][0]['embedding']
