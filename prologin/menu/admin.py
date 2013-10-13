from menu.models import MenuEntry
from django.contrib import admin

class MenuEntryAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'position', 'parent', 'access', 'slug')
    ordering = ['-parent__id', 'position']

admin.site.register(MenuEntry, MenuEntryAdmin)