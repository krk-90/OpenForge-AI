from router import ModelRouter
from langchain_core.messages import SystemMessage, HumanMessage
router = ModelRouter(
    "openai/gpt-oss-20b"
)

prompt = """you are a helpful assistant who answer in short paragraph"""

query = input("Enter the query: ")
messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=query),
    ]

response = router.invoke(messages)

print(response.content)