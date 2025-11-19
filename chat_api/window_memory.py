# window_memory.py
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage

class WindowMemory(BaseChatMessageHistory):
    def __init__(self, k=5):
        self.k = k
        self.messages = []   # LangChain message objects

    def add_user_message(self, text: str):
        self.messages.append(HumanMessage(content=text))
        self._trim()

    def add_ai_message(self, text: str):
        self.messages.append(AIMessage(content=text))
        self._trim()

    def _trim(self):
        """Keep only last k messages."""
        if len(self.messages) > self.k:
            self.messages = self.messages[-self.k:]

    def get_messages(self):
        """Return last k messages."""
        return self.messages

    def clear(self):
        self.messages = []
