from django.db import models
from django.utils import timezone
from django.conf import settings

User = settings.AUTH_USER_MODEL  # 'core.CustomUser'

class StoreSettings(models.Model):
    vendor = models.OneToOneField(User, on_delete=models.CASCADE, related_name='store_settings')
    store_name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='stores/logos/', null=True, blank=True)
    banner = models.ImageField(upload_to='stores/banners/', null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    gst_number = models.CharField(max_length=50, null=True, blank=True)
    bank_account = models.CharField(max_length=100, null=True, blank=True)
    upi_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.vendor.email} store settings"


class Product(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    vendor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=150, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    mrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    images = models.ImageField(upload_to='products/', null=True, blank=True)  # single image; upgrade later to gallery
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)  # vendor disable

    def __str__(self):
        return self.name


class Order(models.Model):
    ORDER_STATUS = (
        ('new', 'New'),
        ('accepted', 'Accepted'),
        ('packed', 'Packed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
    )
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    vendor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vendor_orders')  # denormalized per vendor
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    address = models.TextField()
    tracking_id = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"Order #{self.id} - {self.vendor}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    qty = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # price at order time

    def __str__(self):
        return f"{self.product} x {self.qty}"


class Payout(models.Model):
    vendor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    admin_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=(('pending','Pending'),('paid','Paid')), default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payout #{self.id} to {self.vendor}"


class VendorPayout(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("rejected", "Rejected"),
    ]

    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vendor_payouts"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    admin_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    requested_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def mark_paid(self):
        self.status = "paid"
        self.paid_at = timezone.now()
        self.save()

    def __str__(self):
        return f"Payout #{self.id} - {self.vendor.email} - {self.status}"
