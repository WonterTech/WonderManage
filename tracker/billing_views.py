"""Facturation: factures and bons de livraison."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .activity import changes, describe, log, snapshot
from .billing import ZERO, document_totals
from .forms import CompanyForm, DocumentForm, DocumentLineFormSet
from .inventory import fmt_money
from .models import Document, DocumentLine, InventoryItem, Location, SiteSettings

DOCUMENT_FIELDS = [
    ("client_name", "client"), ("client_location", "lieu client"), ("date", "date"),
    ("due_date", "échéance"), ("status", "statut"),
    ("payment_method", "paiement"), ("stamp_duty", "timbre", "money"), ("withholding_rate", "retenue %"),
    ("notes", "notes"),
]


def _allow(request, codename):
    if not request.user.has_perm(f"tracker.{codename}"):
        raise PermissionDenied


def _snap(document, totals):
    snap = snapshot(document, DOCUMENT_FIELDS)
    if document.kind == Document.Kind.BL:      # these only exist on a facture
        for label in ("échéance", "paiement", "timbre", "retenue %"):
            snap.pop(label, None)
    snap["net à payer"] = fmt_money(totals["net"])
    return snap


def _kind_or_404(kind):
    if kind not in Document.Kind.values:
        raise Http404
    return kind


# ------------------------------------------------------------------ list
@permission_required("tracker.view_document", raise_exception=True)
def document_list(request):
    kind = request.GET.get("kind", "")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    docs = Document.objects.prefetch_related("lines")
    if kind in Document.Kind.values:
        docs = docs.filter(kind=kind)
    if status in Document.Status.values:
        docs = docs.filter(status=status)
    if q:
        match = Q(client_name__icontains=q) | Q(client_tax_id__icontains=q) | Q(notes__icontains=q)
        last = q.rsplit("-", 1)[-1].strip()
        if last.isdigit():                      # "F-2026-0003", "0003" or "3" find that number
            match |= Q(number=int(last))
        docs = docs.filter(match)
    rows = []
    for d in docs[:300]:
        t = document_totals(d)
        rows.append({"d": d, "net": t["net"], "late": d.kind == "facture" and d.status == "validated" and bool(d.due_date and d.due_date < timezone.localdate())})

    # money overview, over all factures that were issued (not drafts, not cancelled)
    unpaid = paid = ZERO
    late = 0
    for d in Document.objects.filter(kind="facture", status__in=["validated", "paid"]).prefetch_related("lines"):
        net = document_totals(d)["net"]
        if d.status == "paid":
            paid += net
        else:
            unpaid += net
            if d.due_date and d.due_date < timezone.localdate():
                late += 1
    return render(request, "tracker/billing_list.html", {
        "rows": rows, "kind": kind, "status": status, "q": q,
        "statuses": Document.Status.choices,
        "unpaid": unpaid, "paid": paid, "late": late,
        "drafts": Document.objects.filter(status="draft").count(),
    })


# ------------------------------------------------------------------ one document
@permission_required("tracker.view_document", raise_exception=True)
def document_detail(request, pk):
    doc = get_object_or_404(Document.objects.prefetch_related("lines"), pk=pk)
    site = SiteSettings.current()
    return render(request, "tracker/billing_detail.html", {
        "doc": doc, "t": document_totals(doc),
        "company": site.company_details,
        "late": doc.kind == "facture" and doc.status == "validated" and bool(doc.due_date and doc.due_date < timezone.localdate()),
        "from_doc": doc.source,
        "converted": list(doc.converted_to.all()),
    })


def document_edit(request, pk=None, kind=None):
    _allow(request, "change_document" if pk else "add_document")
    doc = get_object_or_404(Document, pk=pk) if pk else Document(kind=_kind_or_404(kind))
    before = _snap(doc, document_totals(doc)) if pk else None
    form = DocumentForm(request.POST or None, instance=doc, kind=doc.kind)
    formset = DocumentLineFormSet(request.POST or None, instance=doc)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            saved = form.save()
            formset.instance = saved
            formset.save()
        saved = Document.objects.prefetch_related("lines").get(pk=saved.pk)
        after = _snap(saved, document_totals(saved))
        if pk is None:
            log(request, "created", saved.title, saved.code, describe(after))
        else:
            text = changes(before, after)
            if formset.has_changed() and "net à payer" not in text:
                text = (text + "; " if text else "") + "lignes modifiées"
            if text:
                log(request, "updated", saved.title, saved.code, text)
        return redirect("document_detail", pk=saved.pk)

    names = list(Document.objects.exclude(client_name="").order_by("-date", "-id").values(
        "client_name", "client_address", "client_tax_id", "client_phone", "client_email"))
    clients = {}
    for row in names:
        clients.setdefault(row["client_name"], {
            "address": row["client_address"], "tax_id": row["client_tax_id"],
            "phone": row["client_phone"], "email": row["client_email"],
        })
    stock = [{"name": i.name, "unit": i.unit} for i in InventoryItem.objects.filter(is_active=True).order_by("name")]
    locations = [{"id": p.pk, "name": p.name, "note": p.note} for p in Location.objects.order_by("name")]
    return render(request, "tracker/billing_form.html", {
        "form": form, "formset": formset, "doc": doc, "is_new": pk is None,
        "clients": clients, "stock": stock, "locations": locations,
        "cancel_url": reverse("document_detail", args=[doc.pk]) if pk else reverse("document_list"),
    })


def document_status(request, pk, status):
    _allow(request, "change_document")
    doc = get_object_or_404(Document, pk=pk)
    if request.method != "POST" or status not in Document.Status.values:
        raise Http404
    allowed = {
        "facture": {"draft", "validated", "paid", "cancelled"},
        "bl": {"draft", "delivered", "cancelled"},
    }[doc.kind]
    if status in allowed and status != doc.status:
        old = doc.get_status_display()
        doc.status = status
        doc.save(update_fields=["status", "updated_at"])
        log(request, "updated", doc.title, doc.code, f"statut: {old} -> {doc.get_status_display()}")
    return redirect("document_detail", pk=doc.pk)


def document_convert(request, pk):
    """Turn a bon de livraison into a facture (same client and lines), leaving the bon in place."""
    _allow(request, "add_document")
    bl = get_object_or_404(Document.objects.prefetch_related("lines"), pk=pk, kind="bl")
    if request.method != "POST":
        raise Http404
    with transaction.atomic():
        fac = Document.objects.create(
            kind="facture", date=timezone.localdate(), due_date=timezone.localdate() + timedelta(days=30),
            client_name=bl.client_name, client_address=bl.client_address, client_tax_id=bl.client_tax_id,
            client_phone=bl.client_phone, client_email=bl.client_email,
            client_location=bl.client_location,
            stamp_duty=Decimal("1.000"), notes=bl.notes, source=bl,
        )
        DocumentLine.objects.bulk_create([
            DocumentLine(document=fac, description=l.description, unit=l.unit, quantity=l.quantity,
                         unit_price=l.unit_price, discount_pct=l.discount_pct, vat_rate=l.vat_rate)
            for l in bl.lines.all()
        ])
    log(request, "created", fac.title, fac.code, f"créée depuis {bl.code}")
    return redirect("document_update", pk=fac.pk)


def document_delete(request, pk):
    _allow(request, "delete_document")
    doc = get_object_or_404(Document.objects.prefetch_related("lines"), pk=pk)
    blocked = doc.status not in ("draft", "cancelled")
    if not blocked and request.method == "POST":
        code, title, details = doc.code, doc.title, describe(_snap(doc, document_totals(doc)))
        doc.delete()
        log(request, "deleted", title, code, details)
        return redirect("document_list")
    note = ("Une pièce validée garde son numéro. Passez-la en « Annulé » au lieu de la supprimer."
            if blocked else "Its number will not be reused.")
    return render(request, "tracker/confirm_delete.html", {
        "object": doc, "delete_note": note, "blocked": blocked,
        "cancel_url": reverse("document_detail", args=[doc.pk]),
    })


# ------------------------------------------------------------------ your company's details for the printout
def company_edit(request):
    _allow(request, "change_document")
    site = SiteSettings.load()
    form = CompanyForm(request.POST or None, initial={"company_details": site.company_details})
    if request.method == "POST" and form.is_valid():
        site.company_details = form.cleaned_data["company_details"].strip()
        site.save()
        return redirect("document_list")
    return render(request, "tracker/form.html", {
        "form": form, "page_title": "Mon entreprise", "cancel_url": reverse("document_list"),
    })
