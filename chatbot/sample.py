import requests
import difflib
import re
from django.conf import settings
from .models import Conversation, Message
from .utils import format_prompt
from core.models import Order
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)

HF_HEADERS = {
    "Authorization": f"Bearer {settings.HF_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def is_grocery_context(query):
    q = query.lower()

    grocery_keywords = [
        "fruit", "fruits",
        "vegetable", "veggies",
        "milk", "dairy",
        "meat", "fish", "chicken", "mutton",
        "grocery", "food", "snack"
    ]

    return any(word in q for word in grocery_keywords)


def hf_generate(prompt, max_tokens=200, system_prompt=None, timeout=20):
    """
    Call HF chat completions endpoint. Returns text or raises/returns fallback.
    """
    sys_msg = system_prompt or "Answer using the project data. If unsure, say you don’t know."
    try:
        resp = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers=HF_HEADERS,
            json={
                "model": settings.HF_MODEL,
                "messages": [
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
            },
            timeout=timeout
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.exception("HF generate error")
        return "I'm having trouble fetching info right now."

def levenshtein_distance(a, b):
    if a is None or b is None:
        return max(len(a or ""), len(b or ""))
    a = a.lower()
    b = b.lower()
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous[j + 1] + 1
            deletions = current[j] + 1
            substitutions = previous[j] + (0 if ca == cb else 1)
            current.append(min(insertions, deletions, substitutions))
        previous = current
    return previous[-1]

def smart_match_products(query, project_data, threshold=0.58):
    """
    Fuzzy search across product search_terms and title_lower.
    Returns list of matched product dicts (best-first).
    """
    if not query:
        return []
    q = query.lower().strip().replace(" ", "")
    scores = []
    for p in project_data.get("products", []):
        best = 0.0
        for term in p.get("search_terms", []) + [p.get("title_lower", "")]:
            if not term:
                continue
            t = term.lower().strip().replace(" ", "")

            if q == t or q in t or t in q:
                best = max(best, 1.0)
                break

            ratio = SequenceMatcher(None, q, t).ratio()
            best = max(best, ratio)
        if best >= threshold:
            scores.append((p, best))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [p for p, s in scores]

def advanced_product_match(query, products, top=5):
    q = query.lower()
    scores = []
    for p in products:
        title = p.get("title_lower", "")
        ratio = difflib.SequenceMatcher(None, q, title).ratio()
        if q in title or title in q or ratio >= 0.5:
            scores.append((p, max(ratio, 0.5 if q in title else ratio)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [p for p, s in scores[:top]]

def classify_query_ai(query):
    q = query.lower()
    product_keywords = [
        "price", "offer", "discount", "cost", "kg", "g", "gram", "piece", "ml", "litre",
        "stock", "available", "product", "buy", "order", "cart", "delivery", "slot",
        "fruit", "vegetable", "grocery", "snack", "vetrimart"
    ]
    if any(word in q for word in product_keywords):
        return "vetrimart"

    categories = {
        "movie": ["movie", "film", "actor", "hero", "cinema"],
        "travel": ["travel", "trip", "tour", "hotel"],
        "food": ["recipe", "cook", "dish", "taste"]
    }
    for cat, words in categories.items():
        if any(w in q for w in words):
            return cat
    return "general"

def is_offer_query(query):
    offer_keywords = ["offer", "discount", "sale", "deal", "special price", "today offer"]
    q = query.lower()
    return any(word in q for word in offer_keywords)

def extract_price_filter(query):
    match = re.search(r"(under|below|less than)\s+(\d+)", query.lower())
    if match:
        return int(match.group(2))
    return None

def is_cart_query(query):
    q = query.lower()
    cart_keywords = [
        "cart", "my cart", "items in cart", "what is in my cart",
        "show my cart", "cart items", "tell me my cart"
    ]
    return any(k in q for k in cart_keywords)

def is_wishlist_query(query):
    q = query.lower()
    wishlist_keywords = [
        "wishlist", "my wishlist", "wish list", "items in wishlist",
        "what is in my wishlist", "show my wishlist"
    ]
    return any(k in q for k in wishlist_keywords)

def ai_guess_category(product_name):
    prompt = f"""
    Classify this item into ONE shopping category:
    fruit, vegetable, dairy, meat, beverages, snacks, grocery, other.

    Item: "{product_name}"
    
    Return only the category name.
    """

    try:
        res = hf_generate(prompt) 
        cat = res.strip().lower()

        mapping = {
            "fruits": "fruit",
            "fruit": "fruit",
            "vegetables": "vegetable",
            "vegetable": "vegetable",
            "dairy": "dairy",
            "milk": "dairy",
            "meat": "meat",
            "fish": "meat",
            "snack": "snacks",
            "snacks": "snacks",
            "beverages": "beverages",
            "beverage": "beverages",
            "grocery": "grocery",
            "other": "other"
        }

        return mapping.get(cat, cat)

    except Exception:
        return None

def detect_category_from_query(query, project_data):
    """
    DB-first category detection:
    1) match product titles/search_terms -> product.category
    2) match category names in project_data
    3) fuzzy match product titles (levenshtein / sequence)
    4) AI fallback
    """
    q = (query or "").lower().strip()

    for p in project_data.get("products", []):
        title = p.get("title", "") or ""
        title_low = p.get("title_lower", title.lower())
        if title_low and (title_low in q or q in title_low):
            return p.get("category")
        for term in p.get("search_terms", []):
            t = (term or "").lower().replace(" ", "")
            if t and (t in q.replace(" ", "") or q.replace(" ", "") in t):
                return p.get("category")

    for c in project_data.get("categories", []):
        cname = (c.get("name") or "").lower()
        if cname and cname in q:
            return cname

    best = None
    best_score = 0.0
    for p in project_data.get("products", []):
        t = (p.get("title_lower") or p.get("title", "")).lower().replace(" ", "")
        if not t:
            continue
        seq_ratio = SequenceMatcher(None, q.replace(" ", ""), t).ratio()
        lev = levenshtein_distance(q.replace(" ", ""), t)

        score = seq_ratio - (lev * 0.02)
        if score > best_score:
            best_score = score
            best = p
    if best_score >= 0.5 and best:
        return best.get("category")

    ai_cat = ai_guess_category(query)
    return ai_cat

def format_short_reply(text, query, category):
    import re
    clean = (text or "").replace("\n", " ").strip()
    unknown_phrases = [
        "i don't have", "i do not have", "i’m not sure",
        "i don't know", "no information", "cannot answer", "unknown"
    ]
    fallback_product = "Looks like I couldn’t locate that item — want to see similar choices?"
    fallback_general = "I may not have exact information, but here are some helpful resources."

    if any(p in clean.lower() for p in unknown_phrases):
        short = fallback_product if category == "vetrimart" else fallback_general
    else:
        sentences = re.split(r'(?<=[.!?])\s+', clean)
        short = " ".join(sentences[:2]).strip()
        if len(short) < 3:
            short = fallback_product if category == "vetrimart" else fallback_general

    q = query.replace(" ", "+")
    google = f'<a href="https://www.google.com/search?q={q}" target="_blank">Google</a>'
    images = f'<a href="https://www.google.com/search?tbm=isch&q={q}" target="_blank">Images</a>'
    youtube = f'<a href="https://www.youtube.com/results?search_query={q}" target="_blank">YouTube</a>'

    if category == "movie":
        imdb = f'<a href="https://www.imdb.com/find?q={q}" target="_blank">IMDb</a>'
        return f"{short}<br><br>More: {google} | {images} | {youtube} | {imdb}"

    if category == "travel":
        maps = f'<a href="https://www.google.com/maps/search/{q}" target="_blank">Maps</a>'
        hotels = f'<a href="https://www.booking.com/searchresults.html?ss={q}" target="_blank">Hotels</a>'
        return f"{short}<br><br>Explore: {google} | {images} | {youtube} | {maps} | {hotels}"

    if category == "food":
        recipe = f'<a href="https://www.sanjeevkapoor.com/RecipeSearch.aspx?search={query}" target="_blank">Recipe</a>'
        return f"{short}<br><br>Explore: {google} | {images} | {youtube} | {recipe}"

    if category == "vetrimart":
        return short

    return f"{short}<br><br>Explore: {google} | {images} | {youtube}"

def auto_emoji(query):
    prompt = f"Return ONLY ONE EMOJI for this text: {query}. No words."
    emoji = hf_generate(prompt, max_tokens=8)
    return (emoji or "").strip()[:4]

def clean_query(q):
    remove_words = ["what", "wht", "is", "in", "are", "the", "any", "tell", "me", "show", "please"]
    words = (q or "").lower().split()
    return " ".join([w for w in words if w not in remove_words])

CATEGORY_BENEFITS = {
    "fruit": "Fruits are rich in vitamins, improve immunity, and support digestion.",
    "vegetable": "Vegetables are high in fiber and essential nutrients for overall health.",
    "nuts": "Nuts contain healthy fats, boost brain function, and support heart health.",
    "dairy": "Dairy provides calcium, protein, and strengthens bones.",
    "meat": "Meat is rich in protein and essential minerals for muscle growth.",
    "fish": "Fish is high in omega-3 and supports heart and brain health.",
}

PRODUCT_BENEFITS = {
    "milk": "Milk is rich in calcium and strengthens bones.",
    "apple": "Apples are high in fiber, improve digestion, and support immunity.",
    "banana": "Bananas give instant energy and are rich in potassium.",
    "carrot": "Carrots boost eye health, improve skin glow, and are rich in Vitamin A.",
    "nuts": "Nuts contain healthy fats and support brain & heart health.",
}

def generate_ai_benefits(product_name):
    prompt = (
        f"Give a short friendly description of health benefits or uses of '{product_name}'. "
        "Return only 1–2 sentences."
    )
    text = hf_generate(prompt, max_tokens=60)
    return (text or "").strip()

def save_bot(conversation, user_msg, answer):
    bot_msg = Message.objects.create(
        conversation=conversation,
        sender="bot",
        content=answer
    )
    return {
        "conversation_id": conversation.id,
        "user_message_id": user_msg.id,
        "bot_message_id": bot_msg.id,
        "response": answer,
        "title": conversation.title,
    }

def is_greeting(query):
    greetings = [
        "hi", "hello", "hey", "hai",
        "good morning", "good afternoon", "good evening"
    ]
    q = query.strip().lower()
    return any(q == g or q.startswith(g + " ") for g in greetings)

# def is_project_related(query, matched_products):
#     if matched_products:
#         return True

#     project_keywords = [
#         "price", "offer", "discount", "cart", "wishlist",
#         "buy", "order", "delivery", "stock",
#         "fruit", "vegetable", "grocery", "snack", "vetrimart"
#     ]
#     return any(k in query for k in project_keywords)

def is_project_related(query, matched_products, project_data=None):
    # Normalize once
    q = (query or "").lower().strip()

    # 1️⃣ If product matched → project-related
    if matched_products:
        return True

    # 2️⃣ Keyword-based check
    project_keywords = [
        "price", "offer", "discount", "cart", "wishlist",
        "buy", "order", "delivery", "stock",
        "fruit", "vegetable", "grocery", "snack", "food"
    ]
    if any(k in q for k in project_keywords):
        return True

    if project_data:
        guessed_category = detect_category_from_query(q, project_data)
        if guessed_category:
            return True

    return False

import re

def normalize_text(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)   
    text = re.sub(r"\s+", " ", text) 
    return text.strip()


def is_exact_product_match(query, product):
    q = query.replace(" ", "").lower()
    title = (product.get("title") or "").replace(" ", "").lower()
    return q == title

def get_products_by_category(category, project_data):
    cat = category.lower().rstrip("s")  

    return [
        p for p in project_data.get("products", [])
        if (p.get("category") or "").lower().rstrip("s") == cat
    ]
    
def is_order_query(query):
    order_keywords = [
        "track my order", "track order", "order status",
        "my order", "order details",
        "payment status", "razorpay", "transaction",
        "payment id", "receipt", "invoice"
    ]
    q = query.lower()
    return any(k in q for k in order_keywords)

def is_image_query(query):
    keywords = ["image", "images", "photo", "photos", "picture", "show"]
    q = query.lower()
    return any(k in q for k in keywords)

def is_price_and_image_query(query):
    q = query.lower()
    return ("price" in q) and is_image_query(q)

from difflib import SequenceMatcher

def fuzzy_match(a, b, threshold=0.75):
    return SequenceMatcher(None, a, b).ratio() >= threshold

def fuzzy_ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()


def handle_chat(user, query, conversation=None, project_data=None):
    
    if conversation is None:
        conversation = Conversation.objects.create(user=user)

    if conversation.title == "New Chat":
        conversation.title = query[:30] + "..." if len(query) > 30 else query
        conversation.save()

    user_msg = Message.objects.create(
        conversation=conversation,
        sender="user",
        content=query
    )

    raw_q = normalize_text(query)
    clean_q = clean_query(raw_q)

    # 2️⃣ Greeting
    if is_greeting(raw_q):
        return save_bot(
            conversation,
            user_msg,
            "Hello 👋 Nice to see you! How can I help you today?"
        )

    # 3️⃣ PRICE + IMAGE (must come BEFORE image-only)
    if is_price_and_image_query(raw_q):
        matched_products = smart_match_products(clean_q, project_data) if project_data else []
        matched_products = [
            p for p in matched_products
            if is_exact_product_match(clean_q, p)
        ]

        q = query.replace(" ", "+")

        if matched_products:
            p = matched_products[0]
            answer = (
                f"<b>{p['title']}</b> price is ₹{p['base_price']}<br><br>"
                "View images here:<br>"
                f"🖼️ <a href='https://www.google.com/search?tbm=isch&q={q}' target='_blank'>Google Images</a>"
            )
            return save_bot(conversation, user_msg, answer)

        guessed_category = detect_category_from_query(clean_q, project_data)
        if guessed_category:
            items = get_products_by_category(guessed_category, project_data)
            if items:
                answer = (
                    f"Sorry, we don’t have <b>{query}</b> right now ❌<br><br>"
                    f"<b>Available {guessed_category.title()} items:</b><br>"
                )
                for i in items:
                    answer += f"• {i['title']} — ₹{i['base_price']}<br>"

                answer += (
                    "<br>View images here:<br>"
                    f"🖼️ <a href='https://www.google.com/search?tbm=isch&q={q}' target='_blank'>Google Images</a>"
                )
                return save_bot(conversation, user_msg, answer)

    # 4️⃣ IMAGE ONLY
    if is_image_query(raw_q):
        q = query.replace(" ", "+")
        answer = (
            "I can’t generate images directly, but you can view images here 👇<br><br>"
            f"🖼️ <a href='https://www.google.com/search?tbm=isch&q={q}' target='_blank'>Google Images</a><br>"
            f"📸 <a href='https://www.bing.com/images/search?q={q}' target='_blank'>Bing Images</a><br>"
            f"🎥 <a href='https://www.youtube.com/results?search_query={q}' target='_blank'>YouTube Videos</a>"
        )
        return save_bot(conversation, user_msg, answer)

    # 5️⃣ Order tracking
    if is_order_query(raw_q):
        if user and user.is_authenticated:
            latest_order = (
                Order.objects.filter(user=user)
                .order_by("-created_at")
                .first()
            )

            if not latest_order:
                return save_bot(conversation, user_msg, "You don’t have any orders yet 📦")

            answer = (
                "<b>Order Details</b><br>"
                f"Order ID: {latest_order.id}<br>"
                f"Status: {latest_order.status}<br>"
                f"Amount: ₹{latest_order.total_amount}<br>"
            )

            if latest_order.razorpay_order_id:
                answer += (
                    "<br><b>Payment Details</b><br>"
                    f"Razorpay Order ID: {latest_order.razorpay_order_id}<br>"
                )

            return save_bot(conversation, user_msg, answer)

        return save_bot(conversation, user_msg, "Please log in to track your order 🔐")

    # 6️⃣ Cart
    if project_data and is_cart_query(raw_q):
        if user and user.is_authenticated:
            cart_items = user.cart_items.select_related("product")
            if not cart_items.exists():
                return save_bot(conversation, user_msg, "Your cart is empty 🛒")

            answer = "<b>Your cart items:</b><br>"
            for item in cart_items:
                answer += f"• {item.product.title} × {item.quantity}<br>"

            return save_bot(conversation, user_msg, answer)

        return save_bot(conversation, user_msg, "Please log in to view your cart 😊")

    # 7️⃣ Wishlist
    if project_data and is_wishlist_query(raw_q):
        if user and user.is_authenticated:
            items = user.wishlist.all()
            if not items.exists():
                return save_bot(conversation, user_msg, "Your wishlist is empty ⭐")

            answer = "<b>Your wishlist items:</b><br>"
            for p in items:
                answer += f"• {p.title}<br>"

            return save_bot(conversation, user_msg, answer)

        return save_bot(conversation, user_msg, "Please log in to view wishlist 😊")

    # 8️⃣ Product matching
    matched_products = smart_match_products(clean_q, project_data) if project_data else []
    matched_products = [
        p for p in matched_products
        if is_exact_product_match(clean_q, p)
    ]

    # 9️⃣ Category fallback (banana price case)
    if project_data and not matched_products and is_project_related(raw_q, [], project_data):
        guessed_category = detect_category_from_query(clean_q, project_data)
        if guessed_category:
            items = get_products_by_category(guessed_category, project_data)
            if items:
                answer = (
                    f"Sorry, we don’t have <b>{query}</b> right now ❌<br><br>"
                    f"<b>Available {guessed_category.title()} items:</b><br>"
                )
                for p in items:
                    answer += f"• {p['title']} — ₹{p['base_price']}<br>"

                return save_bot(conversation, user_msg, answer)

    # 🔚 FINAL fallback (only unrelated queries)
    return save_bot(
        conversation,
        user_msg,
        format_short_reply("I don't have this information.", query, "general")
    )




    




    



