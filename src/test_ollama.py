import ollama

resp = ollama.chat(
    model="qwen2.5:7b-instruct",
    messages=[{"role": "user", "content": "Réponds juste: OK"}],
)
print(resp["message"]["content"])