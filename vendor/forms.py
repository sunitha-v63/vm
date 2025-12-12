from django import forms
from .models import Product, StoreSettings

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'category', 'price', 'mrp', 'stock', 'description', 'images']
        widgets = {
            'description': forms.Textarea(attrs={'rows':4}),
        }

from django import forms
from vendor.models import StoreSettings

class StoreSettingsForm(forms.ModelForm):

    class Meta:
        model = StoreSettings
        fields = [
            "store_name", "logo", "banner", "phone",
            "address", "gst_number", "bank_account", "upi_id",
        ]

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        if phone and (len(phone) != 10 or not phone.isdigit()):
            raise forms.ValidationError("Phone number must be 10 digits.")
        return phone

    def clean_gst_number(self):
        gst = self.cleaned_data.get("gst_number")
        if gst and len(gst) != 15:
            raise forms.ValidationError("GST number must be 15 characters.")
        return gst
