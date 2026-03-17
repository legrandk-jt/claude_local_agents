import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
import httpx
from mcp.server.stdio import stdio_server

ollama_base_url = "http://localhost:11434"
default_model = "qwen2.5-coder:14b"
http_timeout = 120

async def ollama_generate(model: str, prompt: str, system: str = "") -> str:
    async with httpx.AsyncClient(timeout=http_timeout) as client:
        try:
            response = await client.post(f"{ollama_base_url}/api/generate", json={"model": model, "prompt": prompt, "system": system, "stream": False})
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            return f"Error: {str(e)}"

async def ollama_chat(model: str, messages: list, system: str = "") -> str:
    async with httpx.AsyncClient(timeout=http_timeout) as client:
        try:
            response = await client.post(f"{ollama_base_url}/api/chat", json={"model": model, "messages": messages, "system": system, "stream": False})
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"

async def ollama_list_models() -> str:
    async with httpx.AsyncClient(timeout=http_timeout) as client:
        try:
            response = await client.get(f"{ollama_base_url}/api/tags")
            response.raise_for_status()
            return "\n".join(tag["name"] for tag in response.json().get("models", []))
        except Exception as e:
            return f"Error: {str(e)}"

server = Server(name="OllamaServer")

@server.list_tools()
async def list_tools():
    return [
        Tool(name="ollama_generate", description="Generate text using a local Ollama model", inputSchema={"type": "object", "properties": {"model": {"type": "string"}, "prompt": {"type": "string"}, "system": {"type": "string"}}}),
        Tool(name="ollama_chat", description="Chat with a local Ollama model", inputSchema={"type": "object", "properties": {"model": {"type": "string"}, "messages": {"type": "array"}, "system": {"type": "string"}}}),
        Tool(name="ollama_list_models", description="List available local Ollama models", inputSchema={"type": "object"})
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "ollama_generate":
        response = await ollama_generate(**arguments)
    elif name == "ollama_chat":
        response = await ollama_chat(**arguments)
    elif name == "ollama_list_models":
        response = await ollama_list_models()
    else:
        return [TextContent(text="Unknown tool", type="text")]
    return [TextContent(text=response, type="text")]

if __name__ == "__main__":
    asyncio.run(stdio_server(server))
