import os
import uuid
import datetime
import json
import re
from typing import Dict, Any
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from dotenv import load_dotenv
import logging
from google import genai
from google.genai import types
from .models import User, Conversation
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

STORE_NAME = os.getenv('STORE_NAME')

MAX_CONTEXT_CHATS = 5

# Gemini Client
try:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("✅ Gemini Client initialized globally")

except Exception as e:
    logger.critical(f"Failed to init Gemini Client: {e}")
    client = None



def get_user_context(user_id: str, user_name: str, limit: int = MAX_CONTEXT_CHATS) -> str:
    try:
        user = User.objects.get(user_id=user_id)
        recent = Conversation.objects.filter(user=user).order_by('-created_at')[:limit]

        if not recent:
            return f"User: {user_name} (New conversation)"

        parts = [f"User Identity: {user_name}\n", "Recent Conversation History:\n"]

        for convo in reversed(recent):
            timestamp = convo.created_at.strftime('%H:%M')
            parts.append(f"[{timestamp}] User: {convo.user_query}")

            resp = convo.bot_response
            short = resp[:500] + "..." if len(resp) > 500 else resp
            parts.append(f"[{timestamp}] Assistant: {short}\n")

        return "\n".join(parts)

    except Exception as e:
        logger.error(f"Context Error: {e}")
        return f"User: {user_name}"



def save_conversation(user_id: str, user_name: str, user_query: str, bot_response: str):
    try:
        user = User.objects.get(user_id=user_id)
        Conversation.objects.create(
            user=user,
            user_query=user_query,
            bot_response=bot_response,
            metadata={
                "query_length": len(user_query),
                "response_length": len(bot_response),
            }
        )

    except Exception as e:
        logger.error(f"Save Conversation Error: {e}")



def format_citations(response_text: str, grounding_metadata: Any) -> str:
    """
    Format citations from grounding metadata.
    CRITICAL: Only add citations, don't modify the response structure.
    """
    if not grounding_metadata or not grounding_metadata.grounding_chunks:
        return response_text

    unique_sources = {}
    
    for chunk in grounding_metadata.grounding_chunks:
        if hasattr(chunk, 'web') and chunk.web:
            uri = chunk.web.uri
            title = chunk.web.title or "Web Source"
            if uri not in unique_sources:
                unique_sources[uri] = title

    if not unique_sources:
        return response_text

    # Format citations
    source_lines = [f"{i}. [{title}]({uri})" 
                   for i, (uri, title) in enumerate(unique_sources.items(), 1)]
    
    footer = "\n\n---\n**📚 Sources:**\n" + "\n".join(source_lines)
    return response_text + footer


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Refined extraction that cleans up 'answer' if follow-ups are merged inside it.
    """
    data = {"answer": "", "follow_up_questions": []}
    
    # --- Step 1: Try to parse JSON (Strategies 1-3 combined) ---
    try:
        # Try direct parse or regex finding the largest JSON object
        json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)
        
        if matches:
            # Use the longest match (most likely the full object)
            best_match = max(matches, key=len)
            parsed = json.loads(best_match)
            
            if isinstance(parsed, dict):
                data["answer"] = parsed.get("answer", parsed.get("response", ""))
                data["follow_up_questions"] = parsed.get("follow_up_questions", [])
        else:
            # Fallback if no JSON object found
            data["answer"] = text
            
    except Exception as e:
        logger.warning(f"JSON Parse failed, using raw text: {e}")
        data["answer"] = text

    # --- Step 2: The Cleanup (Fixing the Merged Text Issue) ---
    # Check if the "answer" text contains the follow-up header due to LLM error
    
    # Common headers LLMs use when slipping out of JSON mode
    split_patterns = [
        r"Here are some follow-up questions:?",
        r"Follow-up questions:?",
        r"Suggested questions:?",
        r"You can ask:?"
    ]
    
    answer_text = data["answer"]
    extracted_questions = []

    for pattern in split_patterns:
        # Look for the pattern (case insensitive)
        split_match = re.search(pattern, answer_text, re.IGNORECASE)
        
        if split_match:
            # Found the split point!
            # 1. Isolate the real answer (everything before the split)
            clean_answer = answer_text[:split_match.start()].strip()
            
            # 2. Isolate the questions text (everything after the split)
            questions_block = answer_text[split_match.end():].strip()
            
            # 3. Extract questions line-by-line or by bullets
            # Regex to find lines starting with -, *, 1., or just newlines
            raw_questions = re.findall(r'(?:^|\n)(?:[-*•]|\d+\.)?\s*(.+?)(?=$|\n)', questions_block)
            
            # Filter out empty strings and keep valid questions
            extracted_questions = [q.strip() for q in raw_questions if len(q.strip()) > 5 and "?" in q]
            
            # Update data
            data["answer"] = clean_answer
            
            # Only overwrite if we actually found questions, otherwise keep existing
            if extracted_questions:
                data["follow_up_questions"] = extracted_questions[:4]
            
            break # Stop checking other patterns if we found one

    # --- Step 3: Final Safety Check ---
    # If we still have no follow-ups, inject generic ones (Optional, keeps UI looking good)
    if not data["follow_up_questions"]:
        data["follow_up_questions"] = [
            "Tell me more about this",
            "What are the tax implications?",
            "Explain in simple terms"
        ]

    return data


# def determine_tool_needed(prompt: str) -> str:
#     """Determine which tool to use based on the query."""
#     prompt_lower = prompt.lower()
    
#     web_keywords = [
#         'latest', 'current', 'today', 'recent', 'news', 'update',
#         'now', 'this year', 'this month', 'budget', 'announcement', 'changes',
#         'rate', 'price', 'stock', 'market', 'what is happening', 'breaking'
#     ]
    
#     file_keywords = [
#         'section', 'act', 'rule', 'provision', 'form', 'itr', 'deduction',
#         '80c', '80d', '80e', 'chapter', 'clause', 'income tax act',
#         'legal', 'law', 'regulation', 'document', 'official', 'procedure'
#     ]
    
#     needs_web = any(keyword in prompt_lower for keyword in web_keywords)
#     needs_files = any(keyword in prompt_lower for keyword in file_keywords)
    
#     if needs_web and not needs_files:
#         return 'google_search'
#     elif needs_files and not needs_web:
#         return 'file_search'
#     elif needs_web and needs_files:
#         return 'google_search'
#     else:
#         return 'file_search' if STORE_NAME else 'none'


class OnboardingView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['name', 'phone'],
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING),
                'phone': openapi.Schema(type=openapi.TYPE_STRING)
            }
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'user_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'name': openapi.Schema(type=openapi.TYPE_STRING),
                    'greeting': openapi.Schema(type=openapi.TYPE_STRING),
                    'follow_ups': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)),
                }
            )
        }
    )
    def post(self, request):
        name = request.data.get("name", "").strip()
        phone = request.data.get("phone", "").strip()

        if not name or not phone:
            return Response({"error": "Name and phone required"}, status=400)

        try:
            user = User.objects.create(
                user_id=str(uuid.uuid4()),
                name=name,
                phone=phone
            )

            greeting = f"Namaste {name}! 🙏 I'm your AI Tax Assistant."

            return Response({
                "user_id": user.user_id,
                "name": user.name,
                "greeting": greeting,
                "follow_ups": [
                    "What is tax on ₹10L income?",
                    "Latest tax slab updates for 2025",
                    "Explain Section 80C deductions",
                    "How to file ITR-1 form?"
                ]
            })

        except Exception as e:
            logger.error(f"Onboarding Error: {e}")
            return Response({"error": "Database error"}, status=500)


class ChatbotView(APIView):
    """Enhanced chatbot with 2-call architecture:
       1. Ask Gemini which tool to use
       2. Use that tool in the real answer
    """
    
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['user_id', 'prompt'],
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_STRING, description="UUID from onboarding"),
                'prompt': openapi.Schema(type=openapi.TYPE_STRING, description="User's tax query")
            }
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'response': openapi.Schema(type=openapi.TYPE_STRING, description="Markdown Answer"),
                    'follow_ups': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)),
                    'tool_used': openapi.Schema(type=openapi.TYPE_STRING, description="google_search / file_search / none"),
                }
            )
        }
    )
    def post(self, request):
        if client is None:
            return Response({"error": "AI service misconfigured"}, status=503)

        user_id = request.data.get("user_id", "").strip()
        prompt = request.data.get("prompt", "").strip()

        if not user_id or not prompt:
            return Response({"error": "User ID and prompt required"}, status=400)

        try:
            user = User.objects.get(user_id=user_id)
            user_name = user.name

            context = get_user_context(user_id, user_name)
            today = datetime.datetime.now().strftime("%d %B %Y")
            
            # CALL #1 — Ask Gemini: Which tool should be used?
          

            tool_decision_instruction = f"""
You are a tool selector AI.

User Query: "{prompt}"

Decide the BEST tool:

- Respond ONLY with one of these: "google_search", "file_search", "none"
- Do NOT add quotes, JSON, explanations, or extra text.
- Only output exactly one word.

Rules:
- Use "google_search" for latest updates, current year rules, news, recent changes.
- Use "file_search" for sections, forms, legal provisions, Income Tax Act references.
- Use "none" for general questions.
"""

            tool_choice_response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=tool_decision_instruction
            )

            tool_raw = tool_choice_response.text.strip().lower()

            # Clean tool output
            if "google" in tool_raw:
                tool_used = "google_search"
            elif "file" in tool_raw:
                tool_used = "file_search"
            else:
                tool_used = "none"

            logger.info(f"🔍 Tool selected by Gemini: {tool_used}")

            
            # CALL #2 — Actual answer with selected tool

            # SYSTEM INSTRUCTION FOR FINAL ANSWER
            system_instruction = f"""
You are an expert Indian Tax Assistant AI. Today is {today}.

**CONTEXT**:
Use conversation history to answer follow-up questions.

**STRICT JSON OUTPUT**:
Return ONLY valid JSON like:
{{"answer": "...", "follow_up_questions": ["q1", "q2", "q3"]}}

No text before or after JSON.
"""

            # BUILD TOOL LIST BASED ON DECISION
            tools_list = []

            if tool_used == "google_search":
                tools_list.append(types.Tool(google_search=types.GoogleSearch()))

            elif tool_used == "file_search":
                tools_list.append(
                    types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[STORE_NAME]
                        )
                    )
                )

            config_args = {
                "system_instruction": system_instruction,
                "temperature": 0.3,
            }

            if tools_list:
                config_args["tools"] = tools_list

            config = types.GenerateContentConfig(**config_args)

            full_prompt = f"{context}\n\n**User Query:** {prompt}"

            # GENERATE FINAL ANSWER
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
                config=config
            )

            # Parse JSON result
            parsed = extract_json_from_text(response.text)
            answer = parsed.get("answer", "")
            follow_ups = parsed.get("follow_up_questions", [])

            # Citations if google search used
            try:
                candidate = response.candidates[0]
                if candidate.grounding_metadata and tool_used == "google_search":
                    answer = format_citations(answer, candidate.grounding_metadata)
                    logger.info("📎 Citations added.")
            except:
                pass

            # Save conversation
            save_conversation(user_id, user_name, prompt, answer)

            return Response({
                "response": answer,
                "follow_ups": follow_ups,
                "tool_used": tool_used
            })

        except Exception as e:
            logger.error(f"Chatbot Error: {e}", exc_info=True)
            return Response({
                "response": "Something went wrong. Please try again.",
                "follow_ups": []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# class ClearChatView(APIView):
#     def post(self, request):
#         user_id = request.data.get("user_id", "").strip()

#         if not user_id:
#             return Response({"error": "User ID required"}, status=400)

#         try:
#             user = User.objects.get(user_id=user_id)
#             Conversation.objects.filter(user=user).delete()

#             return Response({
#                 "status": "success",
#                 "message": "Chat cleared",
#                 "user_name": user.name
#             })

#         except User.DoesNotExist:
#             return Response({"error": "User not found"}, status=404)

#         except Exception as e:
#             logger.error(f"Clear chat error: {e}")
#             return Response({"error": "Failed to clear chat"}, status=500)