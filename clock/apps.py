from django.apps import AppConfig


class ClockConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clock'
    verbose_name = 'Registro Horario'

    def ready(self):
        """Configure SQLite optimizations via connection signal."""
        from django.db.backends.signals import connection_created

        def configure_sqlite(sender, connection, **kwargs):
            if connection.vendor == 'sqlite':
                cursor = connection.cursor()
                # WAL mode: better concurrency for reads/writes
                cursor.execute('PRAGMA journal_mode=WAL;')
                # Synchronous NORMAL: good balance of safety and speed
                cursor.execute('PRAGMA synchronous=NORMAL;')
                # Cache size: 64MB for better performance
                cursor.execute('PRAGMA cache_size=-64000;')

        connection_created.connect(configure_sqlite)
