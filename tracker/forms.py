from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.db.models import Q
from django.db.models.functions import Lower

from . import branding
from .billing import VAT_RATES
from .inventory import average_cost, blank_stats, fmt_qty, item_stats, item_types
from .models import (
    DailyLog, Document, DocumentLine, InventoryItem, Location, Mission, Purchase, Task, TaskMaterial,
)

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "mission", "place", "due_date", "priority",
            "status", "estimated_minutes", "description",
        ]
        labels = {
            "mission": "Mission type",
            "place": "Location",
            "estimated_minutes": "Estimated time (minutes)",
        }
        help_texts = {"mission": "Add new types on the Missions page."}
        widgets = {
            "due_date": DATE,
            "place": forms.HiddenInput(),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mission"].empty_label = "No type"


class MissionForm(forms.ModelForm):
    class Meta:
        model = Mission
        fields = ["title"]
        labels = {"title": "Mission type"}
        widgets = {"title": forms.TextInput(attrs={"placeholder": "e.g. Site visit"})}

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        clash = Mission.objects.filter(title__iexact=title).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have a mission type with this name.")
        return title


class DailyLogForm(forms.ModelForm):
    class Meta:
        model = DailyLog
        fields = ["date", "done", "not_done", "hours_worked", "focus"]
        widgets = {
            "date": DATE,
            "done": forms.Textarea(attrs={"rows": 4}),
            "not_done": forms.Textarea(attrs={"rows": 4}),
        }


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "note", "latitude", "longitude"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Location.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have a location with this name.")
        return name

    def clean(self):
        data = super().clean()
        if (data.get("latitude") is None) != (data.get("longitude") is None):
            raise forms.ValidationError("A pin needs both a latitude and a longitude.")
        return data


class UserForm(forms.ModelForm):
    role = forms.ModelChoiceField(
        queryset=Group.objects.order_by("name"),
        required=False,
        empty_label="No role (can sign in but sees nothing)",
    )
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False), required=False, strip=False
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"is_active": "Account is active (can sign in)"}

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        if self.instance.pk:
            first = self.instance.groups.first()
            self.fields["role"].initial = first.pk if first else None
            self.fields["password"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["password"].required = True
        self.order_fields(["username", "first_name", "last_name", "email", "role", "password", "is_active"])

    def clean_password(self):
        pw = self.cleaned_data.get("password")
        if pw:
            password_validation.validate_password(pw, self.instance)
        return pw

    def clean(self):
        data = super().clean()
        me = self.acting_user
        if me is not None and self.instance.pk and self.instance.pk == me.pk:
            if data.get("is_active") is False:
                raise forms.ValidationError("You can't deactivate your own account.")
            if not me.is_superuser:
                role = data.get("role")
                keeps_access = bool(role) and role.permissions.filter(
                    content_type__app_label="tracker", codename="manage_users"
                ).exists()
                if not keeps_access:
                    raise forms.ValidationError(
                        "You can't take away your own access to user management. Ask another administrator."
                    )
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        user.save()
        role = self.cleaned_data.get("role")
        user.groups.set([role] if role else [])
        return user


class BrandingForm(forms.Form):
    """The Appearance page: site name, colours and logo."""

    site_name = forms.CharField(
        label="Name of the site", max_length=60,
        help_text="Shown at the top of every page and in the browser tab.",
    )
    currency = forms.CharField(
        required=False, max_length=10, label="Currency label",
        help_text="Shown next to prices, e.g. TND, EUR or $. Leave empty to show numbers only.",
    )
    palette = forms.CharField(max_length=20)
    custom_color = forms.CharField(required=False, max_length=7)
    logo = forms.FileField(required=False, label="Logo")
    remove_logo = forms.BooleanField(required=False, label="Remove the current logo")

    def clean_site_name(self):
        name = self.cleaned_data["site_name"].strip()
        if not name:
            raise forms.ValidationError("Please enter a name.")
        return name

    def clean_currency(self):
        return (self.cleaned_data.get("currency") or "").strip()

    def clean_palette(self):
        key = self.cleaned_data["palette"]
        if key not in branding.valid_keys():
            raise forms.ValidationError("Choose one of the colour palettes.")
        return key

    def clean_custom_color(self):
        color = (self.cleaned_data.get("custom_color") or "").strip()
        return color.lower() if branding.HEX.match(color) else ""

    def clean_logo(self):
        upload = self.cleaned_data.get("logo")
        if not upload:
            return None
        if upload.size > branding.MAX_LOGO_BYTES:
            raise forms.ValidationError("The logo is too big. Please use a file under 1 MB.")
        data = upload.read()
        kind = branding.detect_image_type(data)
        if not kind:
            raise forms.ValidationError("Please upload a PNG, JPG, GIF or WebP image.")
        self.logo_bytes, self.logo_type = data, kind
        return upload

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("palette") == "custom" and not cleaned.get("custom_color"):
            self.add_error("custom_color", "Pick a colour.")
        return cleaned


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ["name", "kind", "reference", "unit", "min_stock", "note", "is_active"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "kind": forms.TextInput(attrs={"autocomplete": "off", "placeholder": "Search or type a type"}),
        }

    def clean_kind(self):
        value = " ".join(self.cleaned_data["kind"].split())
        if not value:
            raise forms.ValidationError("Choose a type or type a new one.")
        for existing in item_types():          # reuse the existing spelling (no "material" next to "Material")
            if existing.lower() == value.lower():
                return existing
        return value

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = InventoryItem.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have a product or material with this name.")
        return name

    def clean_unit(self):
        return self.cleaned_data["unit"].strip() or "pcs"


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ["date", "quantity", "unit_price", "supplier", "supplier_location", "note"]
        widgets = {"date": DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier_location"].required = False
        self.fields["supplier_location"].empty_label = "No linked location"


class MaterialChoiceField(forms.ModelChoiceField):
    stats = {}

    def label_from_instance(self, item):
        s = self.stats.get(item.pk) or blank_stats()
        return f"{item.name} ({item.unit}) - {fmt_qty(s['in_stock'])} in stock"


class TaskMaterialForm(forms.ModelForm):
    item = MaterialChoiceField(queryset=InventoryItem.objects.none(), empty_label="Choose a product or material")

    class Meta:
        model = TaskMaterial
        fields = ["item", "quantity", "unit_price", "note"]
        help_texts = {"unit_price": "Leave empty to use the average price paid so far."}

    def __init__(self, *args, show_price=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_price = show_price
        choices = Q(is_active=True)
        if self.instance.pk:
            choices |= Q(pk=self.instance.item_id)   # keep an archived item selectable on lines that already use it
        self.fields["item"].queryset = InventoryItem.objects.filter(choices).order_by(Lower("name"))
        self.fields["item"].stats = item_stats()
        if not show_price:
            del self.fields["unit_price"]

    def save(self, commit=True):
        line = super().save(commit=False)
        if self.show_price:
            if line.unit_price is None:
                line.unit_price = average_cost(line.item)
        elif line._state.adding or "item" in self.changed_data:
            line.unit_price = average_cost(line.item)   # people who can't see prices never type one
        if commit:
            line.save()
        return line


# ------------------------------------------------------------------ facturation
class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            "client_name", "client_address", "client_tax_id", "client_phone", "client_email",
            "client_location", "date", "due_date", "payment_method", "status", "stamp_duty", "withholding_rate", "notes",
        ]
        widgets = {
            "date": DATE, "due_date": DATE,
            "client_name": forms.TextInput(attrs={"list": "client-options", "autocomplete": "off"}),
            "payment_method": forms.TextInput(attrs={"list": "payment-options", "autocomplete": "off"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, kind=None, **kwargs):
        super().__init__(*args, **kwargs)
        kind = kind or self.instance.kind
        S = Document.Status
        allowed = [S.DRAFT, S.VALIDATED, S.PAID, S.CANCELLED] if kind == Document.Kind.FACTURE else [S.DRAFT, S.DELIVERED, S.CANCELLED]
        self.fields["status"].choices = [(v, l) for v, l in S.choices if v in allowed]
        self.fields["client_location"].required = False
        self.fields["client_location"].empty_label = "No linked location"
        if kind == Document.Kind.BL:
            for name in ("due_date", "payment_method", "stamp_duty", "withholding_rate"):
                del self.fields[name]
        elif not self.instance.pk:
            self.initial["stamp_duty"] = "1.000"   # the usual timbre fiscal on a facture; change it freely

    def clean_client_name(self):
        return self.cleaned_data["client_name"].strip()


class DocumentLineForm(forms.ModelForm):
    class Meta:
        model = DocumentLine
        fields = ["description", "unit", "quantity", "unit_price", "discount_pct", "vat_rate"]
        widgets = {
            "description": forms.TextInput(attrs={"list": "stock-options", "autocomplete": "off", "placeholder": "Désignation"}),
            "unit": forms.TextInput(attrs={"placeholder": "pcs"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rates = list(VAT_RATES)
        current = self.instance.vat_rate if self.instance.pk else None
        if current is not None and current not in rates:
            rates.append(current)
        self.fields["vat_rate"].widget = forms.Select(choices=[(f"{r:.2f}", f"{r:g} %") for r in rates])


class BaseLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        kept = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not kept:
            raise forms.ValidationError("Add at least one line.")


DocumentLineFormSet = inlineformset_factory(
    Document, DocumentLine, form=DocumentLineForm, formset=BaseLineFormSet, extra=1, can_delete=True,
)


class CompanyForm(forms.Form):
    company_details = forms.CharField(
        label="Vos coordonnées (en-tête des documents)", required=False,
        widget=forms.Textarea(attrs={"rows": 6, "placeholder": "Raison sociale\nAdresse\nMF : 1234567/A/M/000\nTél : 00 000 000\nEmail"}),
        help_text="Shown at the top of every facture and bon de livraison, line for line as you type it.",
    )
