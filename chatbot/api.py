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

    # Only return True if any grocery keyword exists
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


# -----------------------
# Helpers: matching & fuzzy
# -----------------------
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
        # check defined search_terms (if present)
        for term in p.get("search_terms", []) + [p.get("title_lower", "")]:
            if not term:
                continue
            t = term.lower().strip().replace(" ", "")
            # exact-ish checks
            if q == t or q in t or t in q:
                best = max(best, 1.0)
                break
            # sequence matcher similarity
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


# -----------------------
# Intent detection helpers
# -----------------------
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


# -----------------------
# Category detection (DB first, AI fallback)
# -----------------------
def ai_guess_category(product_name):
    prompt = f"""
    Classify this item into ONE shopping category:
    fruit, vegetable, dairy, meat, beverages, snacks, grocery, other.

    Item: "{product_name}"
    
    Return only the category name.
    """

    try:
        res = hf_generate(prompt)  # ✅ FIXED (remove max_tokens)
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

    # 1) direct product title / search_terms match
    for p in project_data.get("products", []):
        title = p.get("title", "") or ""
        title_low = p.get("title_lower", title.lower())
        # exact contains checks
        if title_low and (title_low in q or q in title_low):
            return p.get("category")
        for term in p.get("search_terms", []):
            t = (term or "").lower().replace(" ", "")
            if t and (t in q.replace(" ", "") or q.replace(" ", "") in t):
                return p.get("category")

    # 2) category name match
    for c in project_data.get("categories", []):
        cname = (c.get("name") or "").lower()
        if cname and cname in q:
            return cname

    # 3) fuzzy match product titles
    best = None
    best_score = 0.0
    for p in project_data.get("products", []):
        t = (p.get("title_lower") or p.get("title", "")).lower().replace(" ", "")
        if not t:
            continue
        seq_ratio = SequenceMatcher(None, q.replace(" ", ""), t).ratio()
        lev = levenshtein_distance(q.replace(" ", ""), t)
        # compute combined heuristic
        score = seq_ratio - (lev * 0.02)
        if score > best_score:
            best_score = score
            best = p
    if best_score >= 0.5 and best:
        return best.get("category")

    # 4) AI fallback
    ai_cat = ai_guess_category(query)
    return ai_cat


# -----------------------
# Reply formatting helpers
# -----------------------
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


# -----------------------
# Main handler (final)
# -----------------------
# def handle_chat(user, query, conversation=None, project_data=None):
#     # Create or reuse conversation
#     if conversation is None:
#         conversation = Conversation.objects.create(user=user)

#     if conversation.title == "New Chat":
#         conversation.title = query[:30] + "..." if len(query) > 30 else query
#         conversation.save()

#     # Save user message
#     user_msg = Message.objects.create(
#         conversation=conversation,
#         sender="user",
#         content=query
#     )

#     # If project data available, prefer project-specific answers
#     if project_data:
#         raw_q = (query or "").lower()
#         clean_q = clean_query(raw_q)

#         # 1) CART intent — handled first to avoid false product matches
#         if is_cart_query(raw_q):
#             if user and getattr(user, "is_authenticated", False):
#                 cart_items = user.cart_items.select_related("product")
#                 if not cart_items.exists():
#                     answer = "Your cart is empty 🛒"
#                 else:
#                     answer = "<b>Your cart items:</b><br>"
#                     for item in cart_items:
#                         prod = item.product
#                         answer += (
#                             f"• <a href='{prod.get_absolute_url()}' target='_blank'>{prod.title}</a>"
#                             f" × {item.quantity}<br>"
#                         )
#             else:
#                 answer = "Please log in to view your cart 😊"
#             return save_bot(conversation, user_msg, answer)

#         # 2) WISHLIST intent
#         if is_wishlist_query(raw_q):
#             if user and getattr(user, "is_authenticated", False):
#                 wish_items = user.wishlist.all()
#                 if not wish_items.exists():
#                     answer = "Your wishlist is empty ⭐"
#                 else:
#                     answer = "<b>Your wishlist items:</b><br>"
#                     for product in wish_items:
#                         answer += (
#                             f"• <a href='{product.get_absolute_url()}' target='_blank'>{product.title}</a><br>"
#                         )
#             else:
#                 answer = "Please log in to view your wishlist 😊"
#             return save_bot(conversation, user_msg, answer)

#         # 3) Smart matching (products)
#         matched_products = smart_match_products(clean_q, project_data)
        
#         if not matched_products and not is_grocery_context(raw_q):
#             raw_answer = hf_generate(query)
#             category = classify_query_ai(query)
#             answer = format_short_reply(raw_answer, query, category)
#             emoji = auto_emoji(query)
#             answer = answer + " " + emoji
#             return save_bot(conversation, user_msg, answer)

#         # 3b) build matched_offers safely
#         offers_list = project_data.get("offers", [])
#         matched_offers = [
#             o for o in offers_list
#             if any(
#                 (o.get("title_lower") or "").lower() == (p.get("title_lower") or "").lower()
#                 for p in matched_products
#             )
#         ]

#         # 4) PRICE query — show primary product price + benefits + link + related suggestions
#         if "price" in raw_q and matched_products:
#             main = matched_products[0]
#             benefit_text = None

#             # product-level manual benefit
#             pname = (main.get("title") or "").lower()
#             for key, val in PRODUCT_BENEFITS.items():
#                 if key in pname:
#                     benefit_text = val
#                     break

#             # category-level benefit
#             if not benefit_text:
#                 cat = (main.get("category") or "").lower()
#                 for key, val in CATEGORY_BENEFITS.items():
#                     if key in cat:
#                         benefit_text = val
#                         break

#             # AI fallback
#             if not benefit_text:
#                 benefit_text = generate_ai_benefits(main.get("title", ""))

#             answer = (
#                 f"The price of <b>{main.get('title')}</b> is ₹{main.get('base_price')}."
#                 f"<br>🛒 <a href='{main.get('url')}' target='_blank'>View Product</a>"
#             )

#             if benefit_text:
#                 answer += f"<br><br>🌿 <b>Benefits:</b> {benefit_text}"

#             # related (same category) suggestions
#             related = [p for p in matched_products[1:10] if p.get("category") == main.get("category")]
#             if related:
#                 answer += "<br><br><b>You may also like:</b><br>"
#                 for p in related:
#                     answer += (
#                         f"• <a href='{p.get('url')}' target='_blank'>{p.get('title')}</a>"
#                         f" — ₹{p.get('base_price')}<br>"
#                     )

#             return save_bot(conversation, user_msg, answer)

#         # 5) OFFER query — if user asks about offers (general or product-specific)
#         if "offer" in raw_q or "discount" in raw_q or is_offer_query(raw_q):
#             # if user typed product words, use matched_offers (product-specific)
#             if matched_offers:
#                 answer = "<b>Available Offers:</b><br>"
#                 for o in matched_offers:
#                     answer += (
#                         f"• <a href='{o.get('url')}' target='_blank'>{o.get('title')}</a>"
#                         f" — {o.get('discount_percent')}% off<br>"
#                     )
#                 return save_bot(conversation, user_msg, answer)

#             # Category-level detection if product not matched
#             guessed_cat = detect_category_from_query(clean_q, project_data)
#             if guessed_cat:
#                 cat_offers = [
#                     o for o in offers_list
#                     if any((p.get("category") or "").lower() == guessed_cat.lower() for p in project_data.get("products", []))
#                 ]
#                 if cat_offers:
#                     answer = f"<b>Offers in {guessed_cat.title()}:</b><br>"
#                     for o in cat_offers:
#                         answer += (
#                             f"• <a href='{o.get('url')}' target='_blank'>{o.get('title')}</a>"
#                             f" — {o.get('discount_percent')}% off<br>"
#                         )
#                     return save_bot(conversation, user_msg, answer)

#             # fallback: show all offers
#             if offers_list:
#                 answer = "<b>Latest Offers:</b><br>"
#                 for o in offers_list:
#                     answer += (
#                         f"• <a href='{o.get('url')}' target='_blank'>{o.get('title')}</a>"
#                         f" — {o.get('discount_percent')}% off<br>"
#                     )
#             else:
#                 answer = "No offers available right now. 😊"
#             return save_bot(conversation, user_msg, answer)

#         # 6) BENEFITS-only query: if user asks about product benefits/uses
#         if any(word in raw_q for word in ["benefit", "benefits", "use", "uses", "help", "good for", "healthy"]):
#             if matched_products:
#                 main = matched_products[0]
#                 product_name = (main.get("title") or "").lower()
#                 category_name = (main.get("category") or "").lower()

#                 # product-level manual benefit
#                 benefit_text = next((v for k, v in PRODUCT_BENEFITS.items() if k in product_name), None)

#                 # category-level benefit
#                 if not benefit_text:
#                     benefit_text = next((v for k, v in CATEGORY_BENEFITS.items() if k in category_name), None)

#                 # AI fallback
#                 if not benefit_text:
#                     benefit_text = generate_ai_benefits(main.get("title", ""))

#                 answer = f"<b>{main.get('title')}</b><br>🌿 {benefit_text}"

#                 # show related same-category suggestions as well
#                 related = [p for p in matched_products[1:10] if p.get("category") == main.get("category")]
#                 if related:
#                     answer += "<br><br><b>You may also like:</b><br>"
#                     for p in related:
#                         answer += (
#                             f"• <a href='{p.get('url')}' target='_blank'>{p.get('title')}</a>"
#                             f" — ₹{p.get('base_price')}<br>"
#                         )

#                 return save_bot(conversation, user_msg, answer)

#         # 7) If products matched -> show main + related (same category) + benefits
#         if matched_products:
#             main = matched_products[0]

#             # Benefits (prefer product → category → AI)
#             benefit_text = next((v for k, v in PRODUCT_BENEFITS.items() if k in main.get("title", "").lower()), None)
#             if not benefit_text:
#                 benefit_text = next((v for k, v in CATEGORY_BENEFITS.items() if k in main.get("category", "").lower()), None)
#             if not benefit_text:
#                 benefit_text = generate_ai_benefits(main.get("title", ""))

#             answer = (
#                 f"<b>{main.get('title')}</b> — ₹{main.get('base_price')}<br>"
#                 f"🛒 <a href='{main.get('url')}' target='_blank'>View Product</a><br><br>"
#             )

#             if benefit_text:
#                 answer += f"🌿 {benefit_text}<br><br>"

#             # RELATED — only same-category products
#             related = [p for p in matched_products[1:10] if p.get("category") == main.get("category")]
#             if related:
#                 answer += "<b>You may also like:</b><br>"
#                 for p in related:
#                     answer += (
#                         f"• <a href='{p.get('url')}' target='_blank'>{p.get('title')}</a>"
#                         f" — ₹{p.get('base_price')}<br>"
#                     )

#             return save_bot(conversation, user_msg, answer)

#         # 8) No matched products -> try category fallback and suggest items
#         guessed_cat = detect_category_from_query(clean_q, project_data)
#         if guessed_cat:
#             same_cat = [p for p in project_data.get("products", []) if (p.get("category") or "").lower() == guessed_cat.lower()]
#             if same_cat:
#                 answer = (
#                     f"We don’t currently sell <b>{query}</b>, but we have similar <b>{guessed_cat.title()}</b> items:<br><br>"
#                 )
#                 for p in same_cat[:8]:
#                     answer += f"• <a href='{p.get('url')}' target='_blank'>{p.get('title')}</a> — ₹{p.get('base_price')}<br>"
#                 return save_bot(conversation, user_msg, answer)

#     # FALLBACK: general AI response (non project-specific)
#     raw_answer = hf_generate(query)
#     category = classify_query_ai(query)
#     answer = format_short_reply(raw_answer, query, category)

#     emoji = auto_emoji(query)
#     answer = answer + " " + emoji

#     return save_bot(conversation, user_msg, answer)

def handle_chat(user, query, conversation=None, project_data=None):
    # Create or reuse conversation
    if conversation is None:
        conversation = Conversation.objects.create(user=user)

    if conversation.title == "New Chat":
        conversation.title = query[:30] + "..." if len(query) > 30 else query
        conversation.save()

    # Save user message
    user_msg = Message.objects.create(
        conversation=conversation,
        sender="user",
        content=query
    )

    raw_q = (query or "").lower()
    clean_q = clean_query(raw_q)

    # ==============================================================
    # 1️⃣ CART INTENT
    # ==============================================================
    if project_data and is_cart_query(raw_q):
        if user and getattr(user, "is_authenticated", False):
            cart_items = user.cart_items.select_related("product")
            if not cart_items.exists():
                answer = "Your cart is empty 🛒"
            else:
                answer = "<b>Your cart items:</b><br>"
                for item in cart_items:
                    prod = item.product
                    answer += (
                        f"• <a href='{prod.get_absolute_url()}' target='_blank'>{prod.title}</a>"
                        f" × {item.quantity}<br>"
                    )
        else:
            answer = "Please log in to view your cart 😊"
        return save_bot(conversation, user_msg, answer)

    # ==============================================================
    # 2️⃣ WISHLIST INTENT
    # ==============================================================
    if project_data and is_wishlist_query(raw_q):
        if user and getattr(user, "is_authenticated", False):
            wish_items = user.wishlist.all()
            if not wish_items.exists():
                answer = "Your wishlist is empty ⭐"
            else:
                answer = "<b>Your wishlist items:</b><br>"
                for product in wish_items:
                    answer += (
                        f"• <a href='{product.get_absolute_url()}' target='_blank'>{product.title}</a><br>"
                    )
        else:
            answer = "Please log in to view your wishlist 😊"
        return save_bot(conversation, user_msg, answer)

    # ==============================================================
    # 3️⃣ MATCH PRODUCTS (SMART MATCH)
    # ==============================================================
    matched_products = smart_match_products(clean_q, project_data) if project_data else []

    # ==============================================================
    # 4️⃣ IF NO PRODUCT MATCH & ALSO NOT GROCERY CONTEXT → AI ANSWER
    # ==============================================================

    if project_data and not matched_products and not is_grocery_context(raw_q):
        raw_answer = hf_generate(query)
        category = classify_query_ai(query)
        answer = format_short_reply(raw_answer, query, category)
        emoji = auto_emoji(query)
        answer = answer + " " + emoji
        return save_bot(conversation, user_msg, answer)

    # ==============================================================
    # 5️⃣ IF NO MATCH BUT GROCERY CONTEXT → GUESS CATEGORY USING AI
    # ==============================================================

    if project_data and not matched_products and is_grocery_context(raw_q):
        ai_cat = ai_guess_category(clean_q)

        if ai_cat:
            similar = [
                p for p in project_data.get("products", [])
                if ai_cat in (p.get("category") or "")
            ]

            if similar:
                answer = (
                    f"We don’t currently sell <b>{query}</b>, "
                    f"but here are similar <b>{ai_cat.title()}</b> items:<br><br>"
                )

                for p in similar[:8]:
                    answer += (
                        f"• <a href='{p['url']}' target='_blank'>{p['title']}</a>"
                        f" — ₹{p['base_price']}<br>"
                    )

                if ai_cat in CATEGORY_BENEFITS:
                    answer += f"<br>🌿 <b>Benefits:</b> {CATEGORY_BENEFITS[ai_cat]}"

                return save_bot(conversation, user_msg, answer)

    # ==============================================================
    # 6️⃣ BUILD MATCHED OFFERS
    # ==============================================================

    offers_list = project_data.get("offers", []) if project_data else []
    matched_offers = [
        o for o in offers_list
        if any(
            (o.get("title_lower") or "").lower() == (p.get("title_lower") or "").lower()
            for p in matched_products
        )
    ]

    # ==============================================================
    # 7️⃣ PRICE QUERY
    # ==============================================================

    if project_data and "price" in raw_q and matched_products:
        main = matched_products[0]
        benefit_text = None

        pname = (main.get("title") or "").lower()

        # product benefit
        benefit_text = PRODUCT_BENEFITS.get(pname)

        # category benefit
        if not benefit_text:
            cat = (main.get("category") or "").lower()
            benefit_text = CATEGORY_BENEFITS.get(cat)

        # AI fallback
        if not benefit_text:
            benefit_text = generate_ai_benefits(main.get("title"))

        answer = (
            f"The price of <b>{main.get('title')}</b> is ₹{main.get('base_price')}."
            f"<br>🛒 <a href='{main.get('url')}' target='_blank'>View Product</a>"
        )

        answer += f"<br><br>🌿 <b>Benefits:</b> {benefit_text}"

        # related products
        related = [
            p for p in matched_products[1:10]
            if p.get("category") == main.get("category")
        ]

        if related:
            answer += "<br><br><b>You may also like:</b><br>"
            for p in related:
                answer += (
                    f"• <a href='{p['url']}' target='_blank'>{p['title']}</a>"
                    f" — ₹{p['base_price']}<br>"
                )

        return save_bot(conversation, user_msg, answer)

    # ==============================================================
    # 8️⃣ OFFER QUERY
    # ==============================================================

    if project_data and ("offer" in raw_q or "discount" in raw_q or is_offer_query(raw_q)):

        # specific product offers
        if matched_offers:
            answer = "<b>Available Offers:</b><br>"
            for o in matched_offers:
                answer += (
                    f"• <a href='{o['url']}' target='_blank'>{o['title']}</a>"
                    f" — {o['discount_percent']}% off<br>"
                )
            return save_bot(conversation, user_msg, answer)

        # fallback: show all offers
        if offers_list:
            answer = "<b>Latest Offers:</b><br>"
            for o in offers_list:
                answer += (
                    f"• <a href='{o['url']}' target='_blank'>{o['title']}</a>"
                    f" — {o['discount_percent']}% off<br>"
                )
            return save_bot(conversation, user_msg, answer)

        return save_bot(conversation, user_msg, "No offers available right now 😊")

    # ==============================================================
    # 9️⃣ BENEFITS QUERY
    # ==============================================================

    if project_data and any(k in raw_q for k in ["benefit", "benefits", "uses", "healthy", "good for"]):
        if matched_products:
            main = matched_products[0]
            pname = (main.get("title") or "").lower()
            cat = (main.get("category") or "").lower()

            benefit = PRODUCT_BENEFITS.get(pname) or CATEGORY_BENEFITS.get(cat)

            if not benefit:
                benefit = generate_ai_benefits(main.get("title"))

            answer = f"<b>{main.get('title')}</b><br>🌿 {benefit}"

            return save_bot(conversation, user_msg, answer)

    # ==============================================================
    # 🔟 PRODUCT MATCH (GENERAL)
    # ==============================================================

    if project_data and matched_products:
        main = matched_products[0]

        pname = (main.get("title") or "").lower()
        cat = (main.get("category") or "").lower()

        benefit = PRODUCT_BENEFITS.get(pname) or CATEGORY_BENEFITS.get(cat)

        if not benefit:
            benefit = generate_ai_benefits(main.get("title"))

        answer = (
            f"<b>{main.get('title')}</b> — ₹{main.get('base_price')}<br>"
            f"🛒 <a href='{main.get('url')}' target='_blank'>View Product</a><br><br>"
            f"🌿 {benefit}<br><br>"
        )

        # related items
        related = [
            p for p in matched_products[1:10]
            if p.get("category") == main.get("category")
        ]

        if related:
            answer += "<b>You may also like:</b><br>"
            for p in related:
                answer += (
                    f"• <a href='{p['url']}' target='_blank'>{p['title']}</a>"
                    f" — ₹{p['base_price']}<br>"
                )

        return save_bot(conversation, user_msg, answer)


    raw_answer = hf_generate(query)
    category = classify_query_ai(query)
    answer = format_short_reply(raw_answer, query, category)
    answer += " " + auto_emoji(query)

    return save_bot(conversation, user_msg, answer)
