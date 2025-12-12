from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum, F
from django.contrib.auth.decorators import login_required

from vendor.decorators import vendor_required
from core.models import Product, Category, Order, OrderItem, Review
from vendor.models import VendorPayout, StoreSettings
from vendor.forms import StoreSettingsForm

# -------------------------
# DASHBOARD
# -------------------------
@login_required
@vendor_required
def vendor_dashboard(request):
    vendor = request.user

    # Product stats
    total_products = Product.objects.filter(vendor=vendor, status='approved').count()
    pending_products = Product.objects.filter(vendor=vendor, status='pending').count()
    rejected_products = Product.objects.filter(vendor=vendor, status='rejected').count()

    # Orders
    vendor_order_items = OrderItem.objects.filter(product__vendor=vendor)
    total_orders = vendor_order_items.values('order').distinct().count()
    pending_orders = vendor_order_items.filter(order__status='pending').values('order').distinct().count()

    # Low stock
    low_stock = Product.objects.filter(vendor=vendor, stock__lt=5, status='approved').count()

    # Earnings
    total_earnings = sum(item.price * item.quantity for item in vendor_order_items)

    # Recent orders
    recent_orders = (
        Order.objects
        .filter(items__product__vendor=vendor)
        .distinct()
        .order_by('-created_at')[:5]
    )

    return render(request, "vendor/dashboard.html", {
        "total_products": total_products,
        "pending_products": pending_products,
        "rejected_products": rejected_products,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "low_stock": low_stock,
        "total_earnings": total_earnings,
        "recent_orders": recent_orders,
    })


# -------------------------
# PRODUCTS LIST
# -------------------------
@login_required
@vendor_required
def vendor_products(request):
    products = Product.objects.filter(vendor=request.user).order_by('-id')
    return render(request, "vendor/products.html", {"products": products})


# -------------------------
# ADD PRODUCT
# -------------------------
@login_required
@vendor_required
def add_product(request):
    categories = Category.objects.all()

    if request.method == "POST":
        stock_value = request.POST.get("stock", 0)

        try:
            stock = int(stock_value)
        except:
            stock = 0

        Product.objects.create(
            vendor=request.user,
            title=request.POST.get("title"),
            category_id=request.POST.get("category"),
            base_price=request.POST.get("base_price"),
            stock=stock,
            unit=request.POST.get("unit"),
            weight_options=request.POST.get("weight_options"),
            description=request.POST.get("description"),
            image=request.FILES.get("image"),
            status="pending",
        )

        messages.success(request, "Product submitted. Waiting for admin approval.")
        return redirect("vendor_products")

    return render(request, "vendor/add_product.html", {
        "categories": categories,
        "product_units": Product.UNIT_CHOICES,
    })


# -------------------------
# EDIT PRODUCT
# -------------------------
@login_required
@vendor_required
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, vendor=request.user)
    categories = Category.objects.all()

    if request.method == "POST":

        # Always allowed fields
        product.base_price = request.POST.get("base_price")
        product.stock = request.POST.get("stock")

        if request.FILES.get("image"):
            product.image = request.FILES["image"]

        # Only editable when NOT approved
        if product.status != "approved":
            product.title = request.POST.get("title", product.title)
            product.category_id = request.POST.get("category", product.category_id)
            product.unit = request.POST.get("unit", product.unit)
            product.weight_options = request.POST.get("weight_options", product.weight_options)
            product.description = request.POST.get("description", product.description)

        product.save()
        messages.success(request, "Product updated successfully.")
        return redirect("vendor_products")

    return render(request, "vendor/edit_product.html", {
        "product": product,
        "categories": categories,
    })


# -------------------------
# DELETE PRODUCT
# -------------------------
@login_required
@vendor_required
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, vendor=request.user)
    product.delete()
    messages.success(request, "Product deleted.")
    return redirect("vendor_products")


# -------------------------
# ORDERS
# -------------------------
@login_required
@vendor_required
def vendor_orders(request):
    vendor = request.user
    orders = Order.objects.filter(items__product__vendor=vendor).distinct()
    return render(request, "vendor/orders.html", {"orders": orders})


# -------------------------
# EARNINGS
# -------------------------
COMMISSION_RATE = 0.10

@login_required
@vendor_required
def vendor_earnings(request):
    vendor = request.user

    vendor_items = OrderItem.objects.filter(product__vendor=vendor, order__status="delivered")

    total_sales = vendor_items.aggregate(total=Sum(F("price") * F("quantity")))["total"] or 0
    commission = total_sales * COMMISSION_RATE
    vendor_amount = total_sales - commission

    payouts = VendorPayout.objects.filter(vendor=vendor).order_by("-requested_at")

    return render(request, "vendor/earnings.html", {
        "total_sales": total_sales,
        "commission": commission,
        "vendor_amount": vendor_amount,
        "payouts": payouts,
    })


@login_required
@vendor_required
def vendor_request_payout(request):
    if request.method == "POST":
        amount = float(request.POST.get("amount", 0))

        vendor = request.user
        vendor_items = OrderItem.objects.filter(product__vendor=vendor, order__status="delivered")

        total_sales = vendor_items.aggregate(total=Sum(F("price") * F("quantity")))["total"] or 0
        commission = total_sales * COMMISSION_RATE
        vendor_balance = total_sales - commission

        if amount > vendor_balance:
            messages.error(request, "You cannot request more than your available balance.")
            return redirect("vendor_earnings")

        VendorPayout.objects.create(
            vendor=vendor,
            amount=amount,
            admin_commission=amount * COMMISSION_RATE,
        )

        messages.success(request, "Payout request submitted.")
        return redirect("vendor_earnings")


# -------------------------
# REVIEWS
# -------------------------
@login_required
@vendor_required
def vendor_reviews(request):
    reviews = Review.objects.filter(product__vendor=request.user).select_related("product", "customer")

    if request.method == "POST":
        review_id = request.POST.get("review_id")
        response = request.POST.get("response")
        r = Review.objects.get(id=review_id, product__vendor=request.user)
        r.response = response
        r.save()
        return redirect("vendor_reviews")

    return render(request, "vendor/reviews.html", {"reviews": reviews})


# -------------------------
# STORE SETTINGS
# -------------------------
@login_required
@vendor_required
def vendor_settings(request):
    settings_obj, created = StoreSettings.objects.get_or_create(vendor=request.user)

    if request.method == "POST":
        form = StoreSettingsForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Store settings updated.")
            return redirect("vendor_settings")
    else:
        form = StoreSettingsForm(instance=settings_obj)

    return render(request, "vendor/settings.html", {"form": form})

@login_required
@vendor_required
def order_detail(request, pk):
    vendor = request.user

    # Get the order only if it has items for this vendor
    order = (
        Order.objects
        .filter(id=pk, items__product__vendor=vendor)
        .distinct()
        .first()
    )

    if not order:
        messages.error(request, "You cannot access this order.")
        return redirect("vendor_orders")

    # Order items only for this vendor
    vendor_items = order.items.filter(product__vendor=vendor)

    return render(request, "vendor/order_detail.html", {
        "order": order,
        "vendor_items": vendor_items,
    })

@login_required
@vendor_required
def vendor_request_payout(request):
    if request.method == "POST":
        amount = float(request.POST.get("amount", 0))

        vendor = request.user
        vendor_items = OrderItem.objects.filter(product__vendor=vendor, order__status="delivered")

        total_sales = vendor_items.aggregate(total=Sum(F("price") * F("quantity")))["total"] or 0
        commission = total_sales * COMMISSION_RATE
        vendor_balance = total_sales - commission

        if amount > vendor_balance:
            messages.error(request, "You cannot request more than your available balance.")
            return redirect("vendor_earnings")

        VendorPayout.objects.create(
            vendor=vendor,
            amount=amount,
            admin_commission=amount * COMMISSION_RATE,
        )

        messages.success(request, "Payout request submitted.")
        return redirect("vendor_earnings")

