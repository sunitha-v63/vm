import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.contrib.auth import get_user_model
from .models import Conversation, Message
from .api import handle_chat
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os

from django.conf import settings
from importlib import import_module
from .utils import format_prompt

from deep_translator import GoogleTranslator



User = get_user_model()  

def chat_page(request):
    return render(request, "chatbot/chat.html")

def load_project_data():
    """
    Loads the project-specific data file (project_chat_data.py)
    that exists in each Django project.
    """
    module = import_module(settings.PROJECT_CHAT_DATA)
    return module.get_project_data()


@csrf_exempt
def chat_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        payload = json.loads(request.body)
    except:
        return HttpResponseBadRequest("Invalid JSON")

    query = payload.get("query")
    cid = payload.get("conversation_id")
    lang = payload.get("lang", "en")

    if not query:
        return JsonResponse({"error": "Missing query"}, status=400)

    translated_query = GoogleTranslator(source="auto", target="en").translate(query)

    conversation = Conversation.objects.filter(id=cid).first()
    user = request.user if request.user.is_authenticated else None

    project_data = load_project_data()

    result = handle_chat(user, translated_query, conversation, project_data)

    translated_response = GoogleTranslator(source="auto", target=lang).translate(result["response"])
    result["response"] = translated_response

    return JsonResponse({
        "conversation_id": result["conversation_id"],
        "user_message_id": result["user_message_id"],
        "bot_message_id": result["bot_message_id"],
        "response": result["response"],
        "title": result["title"],
    })


def all_conversations(request):
    lang = request.GET.get("lang", "en")  

    convos = Conversation.objects.order_by("-pinned", "-created_at")
    data = []

    for c in convos:
        last_msg = c.messages.order_by("-created_at").first()

        if last_msg:
            preview_translated = GoogleTranslator(source="auto", target=lang).translate(last_msg.content)
            preview = preview_translated[:30] + "..."
        else:
            preview = ""

        data.append({
            "id": c.id,
            "title": c.title,
            "pinned": c.pinned,
            "preview": preview,
            "time": c.created_at.strftime("%Y-%m-%d %H:%M")
        })

    return JsonResponse(data, safe=False)


def conversation_messages(request, cid):
    lang = request.GET.get("lang", "en")  

    messages = Message.objects.filter(conversation_id=cid).order_by("created_at")

    data = []

    for m in messages:
        translated_text = GoogleTranslator(source="auto", target=lang).translate(m.content)

        data.append({
            "id": m.id,
            "sender": m.sender,
            "content": translated_text
        })

    return JsonResponse(data, safe=False)

@csrf_exempt
@require_POST
def delete_conversation(request, cid):
    convo = get_object_or_404(Conversation, id=cid)

    cache.set(f"deleted_convo_{cid}", {
        "title": convo.title,
        "user_id": convo.user_id,
        "created_at": convo.created_at,
    }, timeout=15)

    convo.delete()
    return JsonResponse({"deleted": True})
DELETED_CHATS = {}

@csrf_exempt
@require_POST
def restore_conversation(request, cid):
    data = cache.get(f"deleted_convo_{cid}")

    if not data:
        return JsonResponse({"restored": False})

    new_convo = Conversation.objects.create(
        id=cid,             
        title=data["title"],
        user_id=data["user_id"],
        created_at=data["created_at"],
    )

    return JsonResponse({"restored": True})


@csrf_exempt
def rename_conversation(request, cid):
    data = json.loads(request.body)
    title = data.get("title")

    if not title:
        return JsonResponse({"error": "Missing title"}, status=400)

    try:
        conv = Conversation.objects.get(id=cid)
        conv.title = title
        conv.save()
        return JsonResponse({"renamed": True})
    except Conversation.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

@csrf_exempt
def pin_conversation(request, cid):
    try:
        conv = Conversation.objects.get(id=cid)
        conv.pinned = not conv.pinned
        conv.save()
        return JsonResponse({"pinned": conv.pinned})
    except Conversation.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)


@csrf_exempt
def upload_file(request):
    file = request.FILES.get("file")
    conv_id = request.POST.get("conversation_id")

    if not file:
        return JsonResponse({"error": "Missing file"}, status=400)

    if conv_id:
        try:
            conversation = Conversation.objects.get(id=conv_id)
        except Conversation.DoesNotExist:
            conversation = Conversation.objects.create(
                user=request.user if request.user.is_authenticated else None
            )
            conv_id = conversation.id
    else:
        conversation = Conversation.objects.create(
            user=request.user if request.user.is_authenticated else None
        )
        conv_id = conversation.id

    upload_path = os.path.join(settings.MEDIA_ROOT, "uploads")
    os.makedirs(upload_path, exist_ok=True)

    fs = FileSystemStorage(
        location=upload_path,
        base_url=settings.MEDIA_URL + "uploads/"
    )

    filename = fs.save(file.name, file)
    file_url = fs.url(filename)

    if file.content_type.startswith("image/"):
        img_html = f'<img src="{file_url}" class="uploaded-img">'
        content = img_html
        bot_reply = "I received your image!"
    else:
        img_html = None
        content = f"📎 {file.name}"
        bot_reply = "I received your file!"

    # Create user message
    user_msg = Message.objects.create(
        conversation=conversation,
        sender="user",
        content=content
    )

    # Bot reply
    bot_msg = Message.objects.create(
        conversation=conversation,
        sender="bot",
        content=bot_reply
    )

    return JsonResponse({
        "response": bot_msg.content,
        "image_html": img_html,
        "message_id": user_msg.id,
        "bot_message_id": bot_msg.id,
        "conversation_id": conv_id
    })

@csrf_exempt
@require_POST
def delete_message(request, mid):
    try:
        msg = Message.objects.get(id=mid)
        msg.delete()
        return JsonResponse({"deleted": True})
    except Message.DoesNotExist:
        return JsonResponse({"error": "Message not found"}, status=404)
