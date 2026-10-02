"""Not Spark code: a Django-style queryset filter is out of scope."""

from myapp.models import Order

orders = Order.objects.filter(created__gte="2026-01-01")
