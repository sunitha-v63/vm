from django.contrib import admin
from .models import Product, Order, OrderItem, Payout,  StoreSettings

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id','name','vendor','price','stock','status','created_at')
    list_filter = ('status','created_at')
    actions = ['approve_products','reject_products']

    def approve_products(self, request, queryset):
        queryset.update(status='approved')
    approve_products.short_description = "Approve selected products"

    def reject_products(self, request, queryset):
        queryset.update(status='rejected')
    reject_products.short_description = "Reject selected products"

admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Payout)
admin.site.register(StoreSettings)


from vendor.models import VendorPayout
from django.contrib import admin
from django.utils import timezone

@admin.register(VendorPayout)
class VendorPayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "amount", "admin_commission", "status", "requested_at", "paid_at")
    list_filter = ("status",)
    search_fields = ("vendor__email",)

    actions = ["approve_payout", "mark_as_paid"]

    def approve_payout(self, request, queryset):
        queryset.update(status="approved")
    approve_payout.short_description = "Approve selected payout requests"

    def mark_as_paid(self, request, queryset):
        queryset.update(status="paid", paid_at=timezone.now())
    mark_as_paid.short_description = "Mark selected requests as PAID"
