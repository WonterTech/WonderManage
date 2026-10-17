from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Max
from django.utils import timezone


class Mission(models.Model):
    """A type of mission, e.g. "Site visit" or "Client meeting". Just a name."""

    title = models.CharField("Mission type", max_length=200)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Location(models.Model):
    """A place you work at or visit. The map pin (latitude/longitude) is optional."""

    name = models.CharField(max_length=200)
    note = models.CharField("Address or note", max_length=300, blank=True)
    latitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def has_pin(self):
        return self.latitude is not None and self.longitude is not None


class Task(models.Model):
    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        MEDIUM = 2, "Medium"
        HIGH = 3, "High"

    class Status(models.TextChoices):
        TODO = "todo", "To do"
        DOING = "doing", "In progress"
        DONE = "done", "Done"

    # Tasks are identified by a number that goes up by one for each new task (T-0001, T-0002, ...).
    # `title` is only kept so that tasks created before numbering still show their old name.
    number = models.PositiveIntegerField(null=True, blank=True, unique=True, editable=False)
    title = models.CharField(max_length=200, blank=True)
    mission = models.ForeignKey(
        Mission, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    place = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.IntegerField(choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO)
    estimated_minutes = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["due_date", "-priority", "id"]
        # Not about tasks themselves: this is the permission that opens the "Users and roles" pages.
        permissions = [("manage_users", "Can manage users and roles")]

    def __str__(self):
        return self.display_title

    @property
    def code(self):
        return f"T-{self.number:04d}" if self.number else "T-new"

    @property
    def display_title(self):
        return f"{self.code} · {self.title}" if self.title else self.code

    @property
    def is_overdue(self):
        return bool(self.status != self.Status.DONE and self.due_date and self.due_date < timezone.localdate())

    def save(self, *args, **kwargs):
        if self.number is None:
            self.number = Sequence.next_number("task")
        if self.status == self.Status.DONE:
            if not self.completed_at:
                self.completed_at = timezone.now()
        else:
            self.completed_at = None
        super().save(*args, **kwargs)


class DailyLog(models.Model):
    """End-of-day journal: what got done, what didn't, and how long you worked."""

    date = models.DateField(unique=True, default=timezone.localdate)
    done = models.TextField("What I did", blank=True)
    not_done = models.TextField("What I didn't get to", blank=True)
    hours_worked = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    focus = models.PositiveSmallIntegerField(
        "Focus (1-5)", null=True, blank=True, help_text="How focused were you today?"
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"Log {self.date}"


class SiteSettings(models.Model):
    """One row: the name, logo and colours of this installation (set on the Appearance page)."""

    site_name = models.CharField(max_length=60, default="Work log")
    palette = models.CharField(max_length=20, default="original")
    custom_color = models.CharField(max_length=7, default="#1d4ed8")
    logo_data = models.BinaryField(null=True, blank=True)
    logo_type = models.CharField(max_length=30, blank=True, default="")
    currency = models.CharField(max_length=10, blank=True, default="")
    company_details = models.TextField(blank=True, default="")   # printed at the top of factures / bons de livraison
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        """The saved settings, or an unsaved default row if none were saved yet (never writes)."""
        return cls.objects.first() or cls()

    @classmethod
    def load(cls):
        site = cls.objects.first()
        return site or cls.objects.create()


class Sequence(models.Model):
    """Counters that only go up, so a number is never given out twice (even after a delete)."""

    name = models.CharField(max_length=30, unique=True)
    last = models.PositiveIntegerField(default=0)

    @classmethod
    def next_number(cls, name):
        with transaction.atomic():
            start = 0
            if name == "task":
                start = Task.objects.aggregate(m=Max("number"))["m"] or 0
            seq, _ = cls.objects.get_or_create(name=name, defaults={"last": start})
            cls.objects.filter(pk=seq.pk).update(last=F("last") + 1)   # takes the write lock first
            return cls.objects.get(pk=seq.pk).last


_QTY = [MinValueValidator(Decimal("0.01"))]


class InventoryItem(models.Model):
    """A product or a material you keep in stock."""

    DEFAULT_TYPES = ["Material", "Product"]

    name = models.CharField(max_length=200)
    # Free text: you pick an existing type or add your own (the form asks before creating a new one).
    kind = models.CharField("Type", max_length=60, default="Material")
    reference = models.CharField("Reference / code", max_length=60, blank=True)
    unit = models.CharField(max_length=20, default="pcs", help_text="How it is counted: pcs, kg, m, L, box...")
    min_stock = models.DecimalField(
        "Warn me when stock is at or below", max_digits=12, decimal_places=2, null=True, blank=True
    )
    note = models.TextField(blank=True)
    is_active = models.BooleanField(
        "Active", default=True, help_text="Untick to hide it from the list when adding materials to a task. Nothing is deleted."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        permissions = [("view_costs", "Can see purchase prices and costs")]

    def __str__(self):
        return self.name


class Purchase(models.Model):
    """Stock bought: how many, and the price paid per unit."""

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="purchases")
    date = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=_QTY)
    unit_price = models.DecimalField(
        "Price per unit", max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0"))]
    )
    supplier = models.CharField(max_length=200, blank=True)
    supplier_location = models.ForeignKey(
        "Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="supplier_purchases",
        verbose_name="Supplier location",
    )
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.item.name} x {self.quantity} on {self.date}"

    @property
    def total(self):
        return self.quantity * self.unit_price


class TaskMaterial(models.Model):
    """Material used on a task. The unit price is kept as it was when the material was used."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="materials")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="usages")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=_QTY)
    unit_price = models.DecimalField(
        "Cost per unit", max_digits=12, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    note = models.CharField(max_length=300, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.item.name} x {self.quantity} on {self.task.code}"

    @property
    def line_total(self):
        return self.quantity * (self.unit_price or Decimal("0"))


class ActivityLog(models.Model):
    """Who changed what, and when. Written by the app; there is no screen to edit or delete it."""

    when = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=12)
    kind = models.CharField(max_length=30)
    target = models.CharField(max_length=200)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-when", "-id"]

    def __str__(self):
        return f"{self.when:%Y-%m-%d %H:%M} {self.username} {self.action} {self.kind} {self.target}"


class Document(models.Model):
    """A facture (invoice) or a bon de livraison (delivery note) with its client and money details."""

    class Kind(models.TextChoices):
        FACTURE = "facture", "Facture"
        BL = "bl", "Bon de livraison"

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        VALIDATED = "validated", "Validé"
        PAID = "paid", "Payé"
        DELIVERED = "delivered", "Livré"
        CANCELLED = "cancelled", "Annulé"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.FACTURE)
    year = models.PositiveSmallIntegerField(editable=False)
    number = models.PositiveIntegerField(editable=False)
    date = models.DateField("Date", default=timezone.localdate)
    due_date = models.DateField("Échéance", null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    client_name = models.CharField("Client", max_length=200)
    client_address = models.CharField("Adresse", max_length=300, blank=True)
    client_tax_id = models.CharField("Matricule fiscal", max_length=60, blank=True)
    client_phone = models.CharField("Téléphone", max_length=40, blank=True)
    client_email = models.CharField("Email", max_length=120, blank=True)
    client_location = models.ForeignKey(
        "Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="client_documents",
        verbose_name="Client location",
    )

    payment_method = models.CharField("Mode de paiement", max_length=60, blank=True)
    stamp_duty = models.DecimalField(
        "Timbre fiscal", max_digits=8, decimal_places=3, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    withholding_rate = models.DecimalField(
        "Retenue à la source (%)", max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    notes = models.TextField("Notes", blank=True)
    source = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="converted_to", editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [models.UniqueConstraint(fields=["kind", "year", "number"], name="unique_document_number")]

    def __str__(self):
        return self.code

    @property
    def prefix(self):
        return "F" if self.kind == self.Kind.FACTURE else "BL"

    @property
    def code(self):
        return f"{self.prefix}-{self.year}-{self.number:04d}" if self.number else f"{self.prefix}-new"

    @property
    def title(self):
        return self.get_kind_display()

    def save(self, *args, **kwargs):
        if not self.number:
            self.year = (self.date or timezone.localdate()).year
            self.number = Sequence.next_number(f"{self.kind}-{self.year}")
        super().save(*args, **kwargs)


class DocumentLine(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField("Désignation", max_length=300)
    unit = models.CharField("Unité", max_length=20, blank=True, default="")
    quantity = models.DecimalField("Qté", max_digits=12, decimal_places=2, default=Decimal("1"), validators=_QTY)
    unit_price = models.DecimalField(
        "P.U. HT", max_digits=12, decimal_places=3, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    discount_pct = models.DecimalField(
        "Remise %", max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    vat_rate = models.DecimalField(
        "TVA %", max_digits=5, decimal_places=2, default=Decimal("19.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} x {self.quantity}"
