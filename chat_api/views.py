from django.shortcuts import render

# Create your views here.
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import google.generativeai as genai
import os
from langchain_core.messages import HumanMessage, AIMessage
from .window_memory import WindowMemory 
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
memory = WindowMemory(k=5)
class ChatbotView(APIView):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction="""
                You are a helpful Indian tax assistant.
                Always respond clearly, in bullet points or short sections.
                Do not use markdown formatting.
                """
            )
        except Exception as e:
            print(f"Error configuring GenerativeAI: {e}")
            self.model = None

    def post(self, request, *args, **kwargs):
        if not self.model:
            return Response({"error": "Model not initialized"}, status=500)

        prompt = request.data.get("prompt")
        if not prompt:
            return Response({"error": "Prompt required"}, status=400)

        # 🧠 Save user message to memory
        memory.add_user_message(prompt)

        # 🧠 Get last 5 messages
        history = memory.get_messages()

        # 🔄 Convert LangChain messages to usable text
        context = ""
        for msg in history:
            if isinstance(msg, HumanMessage):
                context += f"User: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                context += f"Assistant: {msg.content}\n"

        final_prompt = f"""
                    Use the conversation history below for context:
                    {context}
                    
                    User now asks:
                    {prompt}
                    
                    Use your own web search to be updated.Respond based on chat so far.
                            """

        try:
            response = self.model.generate_content(final_prompt)
            answer = response.text.strip()

            # 💾 Save assistant reply to memory
            memory.add_ai_message(answer)

            return Response({"response": answer}, status=200)

        except Exception as e:
            print("Gemini error:", e)
            return Response({"error": str(e)}, status=500)
        
class ClearChatView(APIView):
    def post(self, request):
        memory.clear()
        return Response({"status": "chat memory cleared"})