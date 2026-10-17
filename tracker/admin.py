from django.contrib import admin
from .models import DailyLog, Location, Mission, Task

admin.site.register(Mission)
admin.site.register(Location)
admin.site.register(Task)
admin.site.register(DailyLog)
