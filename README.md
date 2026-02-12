# Meriendahaus Zeiterfassung

Sistema de control de asistencia (fichaje) para empleados de Meriendahaus.

![Status](https://img.shields.io/badge/status-en%20desarrollo-yellow)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/django-5.x-green)

---

## Estado del Proyecto

| Componente | Estado | Descripcion |
|------------|--------|-------------|
| Modelos de datos | Completo | Location, TimeEntry con historial |
| Panel de empleados | Completo | Login, fichaje entrada/salida |
| Validacion IP | Completo | Anti-fraude por geolocalizacion |
| Panel Admin | Completo | Dashboard, reportes, CRUD |
| Interfaz UI | Completo | Tema oscuro estilo GitHub |
| Generacion QR | Completo | Para identificar locales |
| Tests | Pendiente | Unit tests y integration tests |
| Despliegue | Pendiente | Configuracion produccion |

---

## Descripcion General

Sistema web para que los empleados registren sus horas de trabajo mediante:
- **Fichaje por QR**: Escanean codigo QR del local
- **Validacion por IP**: Solo permite fichar desde la red del establecimiento
- **Panel administrativo**: Dashboard con estadisticas, reportes y gestion

### Caracteristicas principales

- Fichaje de entrada/salida con validacion geografica (IP)
- Dashboard administrativo con estadisticas en tiempo real
- Historial completo de cambios (audit trail)
- Generacion de codigos QR para locales
- Reportes de horas por empleado (semanal/mensual)
- Cierre automatico de fichajes olvidados
- Interfaz responsive (movil y escritorio)

---

## Arquitectura

```
meriendahaus_Zeiterfassung/
├── zeiterfassung/          # Proyecto Django principal
│   ├── settings.py         # Configuracion
│   ├── urls.py             # URLs principales
│   └── wsgi.py             # WSGI para produccion
├── clock/                  # App principal de fichajes
│   ├── models.py           # Modelos: Location, TimeEntry
│   ├── views.py            # Vistas de empleados
│   ├── admin_views.py      # Vistas del panel admin
│   ├── admin.py            # Configuracion Django Admin
│   ├── ip_utils.py         # Utilidades validacion IP
│   ├── urls.py             # URLs empleados
│   └── admin_urls.py       # URLs panel admin
├── templates/              # Templates globales
│   └── admin/
│       └── base_site.html  # Template base admin personalizado
├── static/                 # Archivos estaticos
│   └── img/                # Logos e imagenes
└── db.sqlite3              # Base de datos SQLite
```

---

## Modelos de Datos

### Location (Local)
Representa un establecimiento fisico donde los empleados pueden fichar.

```python
class Location(models.Model):
    code = models.CharField(max_length=20, unique=True)  # Ej: "LOCAL_01"
    name = models.CharField(max_length=100)               # Ej: "Meriendahaus Principal"
    allowed_ips = models.JSONField(default=list)          # IPs permitidas
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords()                         # Audit trail
```

**Logica**:
- `allowed_ips` contiene lista de IPs o rangos CIDR permitidos
- Solo se puede fichar si la IP del usuario esta en la lista
- Soporta IPs individuales (`"85.123.45.67"`) y rangos (`"192.168.1.0/24"`)

### TimeEntry (Fichaje)
Representa un registro de entrada/salida de un empleado.

```python
class TimeEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    check_in = models.DateTimeField()              # Hora entrada
    check_out = models.DateTimeField(null=True)    # Hora salida (null = abierto)
    check_in_ip = models.GenericIPAddressField()   # IP de entrada
    check_out_ip = models.GenericIPAddressField(null=True)
    is_manual = models.BooleanField(default=False) # Editado por admin
    notes = models.TextField(blank=True)           # Notas/razones
    modified_by = models.ForeignKey(User, null=True)
    history = HistoricalRecords()                  # Audit trail
```

**Propiedades calculadas**:
- `is_open`: True si no tiene check_out
- `duration_minutes`: Duracion en minutos
- `duration_display`: Formato "Xh XXm"

---

## Sistema de Validacion IP

### Flujo de fichaje

```
1. Empleado escanea QR o ingresa codigo → "LOCAL_01"
2. Sistema obtiene IP real del cliente
3. Busca Location con ese codigo
4. Compara IP contra location.allowed_ips
5. Si coincide → Permite fichaje
6. Si no coincide → Error "No puedes fichar desde fuera del local"
```

### Obtencion de IP real (`ip_utils.py`)

Prioridad de deteccion:
1. `X-Real-IP` (configurado por Nginx)
2. `X-Forwarded-For` (primer IP de la cadena)
3. `REMOTE_ADDR` (conexion directa)

```python
def get_client_ip(request):
    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return x_real_ip

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()

    return request.META.get('REMOTE_ADDR', '0.0.0.0')
```

### Validacion de IP permitida

```python
def is_ip_allowed(client_ip, allowed_list):
    client_addr = ipaddress.ip_address(client_ip)

    for allowed in allowed_list:
        if '/' in allowed:
            # Rango CIDR
            network = ipaddress.ip_network(allowed, strict=False)
            if client_addr in network:
                return True
        else:
            # IP individual
            if client_addr == ipaddress.ip_address(allowed):
                return True

    return False
```

---

## Panel de Empleados

### URLs

| URL | Vista | Descripcion |
|-----|-------|-------------|
| `/` | `clock_view` | Pantalla principal de fichaje |
| `/login/` | `login_view` | Inicio de sesion |
| `/logout/` | `logout_view` | Cerrar sesion |
| `/api/status/` | `status_api` | JSON con estado actual |

### Flujo de uso

1. Empleado inicia sesion con usuario/contrasena
2. Ve pantalla de fichaje con estado actual
3. Escanea QR del local (o ingresa codigo manualmente)
4. Presiona "Entrada" o "Salida"
5. Sistema valida IP y registra fichaje
6. Muestra confirmacion o error

---

## Panel Administrativo

### URLs Custom (Dashboard)

| URL | Vista | Descripcion |
|-----|-------|-------------|
| `/admin/clock/dashboard/` | `admin_dashboard` | Dashboard principal |
| `/admin/clock/who-is-here/` | `who_is_here` | Empleados presentes ahora |
| `/admin/clock/hours-summary/` | `hours_summary` | Resumen de horas |
| `/admin/clock/employee/<id>/` | `employee_detail` | Detalle de empleado |
| `/admin/clock/calendar/` | `calendar_view` | Vista calendario mensual |
| `/admin/clock/close-forgotten/` | `close_forgotten_entries` | Cerrar fichajes olvidados |
| `/admin/clock/location/<id>/qr/` | `generate_qr` | Generar codigo QR |
| `/admin/clock/location/<id>/qr-print/` | `qr_print_page` | Pagina imprimible QR |

### Django Admin (CRUD)

| URL | Descripcion |
|-----|-------------|
| `/admin/clock/timeentry/` | Gestion de fichajes |
| `/admin/clock/location/` | Gestion de locales |
| `/admin/auth/user/` | Gestion de usuarios |

### Dashboard - Funcionalidades

El dashboard muestra:
- **Estadisticas del dia**: Fichajes totales, completados, abiertos, manuales
- **Estadisticas de la semana**: Horas totales, empleados unicos
- **Alertas**: Fichajes olvidados (dias anteriores sin cerrar)
- **Fichajes largos**: Entradas abiertas >12 horas (posible olvido)
- **Horas extra**: Fichajes >8 horas
- **Entradas manuales recientes**: Requieren revision

### Otras vistas admin

- **Quien esta aqui**: Lista empleados actualmente fichados con duracion
- **Resumen de horas**: Por semana/mes con totales por empleado
- **Calendario**: Vista mensual de todos los fichajes
- **Cerrar olvidados**: Cierra automaticamente fichajes de dias anteriores a las 23:59
- **Generador QR**: Crea codigos QR PNG/SVG para cada local

---

## Interfaz de Usuario

### Tema Visual

Estilo inspirado en GitHub con tema **oscuro exclusivo**:

```css
:root {
    --color-canvas-default: #0d1117;     /* Fondo principal */
    --color-canvas-subtle: #161b22;       /* Fondo secundario */
    --color-border-default: #30363d;      /* Bordes */
    --color-fg-default: #e6edf3;          /* Texto principal */
    --color-fg-muted: #8d96a0;            /* Texto secundario */
    --color-accent-fg: #4493f8;           /* Links/acentos azul */
    --color-success-fg: #3fb950;          /* Verde exito */
    --color-attention-fg: #d29922;        /* Amarillo advertencia */
    --color-danger-fg: #f85149;           /* Rojo error */
    --color-btn-primary-bg: #238636;      /* Boton primario verde */
}
```

### Componentes UI

- **Header**: Barra fija 48px con logo horizontal blanco + boton menu
- **Sidebar**: Menu lateral deslizable desde la derecha (280px)
- **Cards**: Contenedores con fondo oscuro y bordes sutiles
- **Tablas**: Con hover, bordes redondeados, headers destacados
- **Badges**: Estados con colores semanticos (success, warning, danger)
- **Alertas**: Mensajes con iconos SVG y borde lateral de color
- **Botones**: Estilo GitHub con hover states

### Archivos de estilo

| Archivo | Proposito |
|---------|-----------|
| `templates/admin/base_site.html` | Estilos globales del admin (~700 lineas CSS) |
| `clock/templates/admin/clock/admin_base.html` | Estilos adicionales para dashboard |
| `static/img/logo-horizontal-white.png` | Logo horizontal blanco para header |

---

## Tecnologias

| Componente | Tecnologia |
|------------|------------|
| Backend | Django 5.x |
| Base de datos | SQLite3 |
| Historial | django-simple-history |
| QR Codes | qrcode + Pillow |
| Frontend | HTML/CSS vanilla (sin frameworks) |
| Iconos | SVG inline (estilo Heroicons) |

### Dependencias principales

```
django>=5.0
django-simple-history
python-dotenv
qrcode[pil]
```

---

## Instalacion

### Requisitos previos

- Python 3.12+
- pip

### Pasos

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd meriendahaus_Zeiterfassung

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# 5. Aplicar migraciones
python manage.py migrate

# 6. Crear superusuario (admin)
python manage.py createsuperuser

# 7. Ejecutar servidor desarrollo
python manage.py runserver
```

### Variables de entorno (`.env`)

```env
SECRET_KEY=tu-clave-secreta-super-larga-aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
TZ=Europe/Berlin
```

---

## Configuracion Inicial

### 1. Crear Location (Local)

Opcion A - Via Django Admin:
1. Ir a `/admin/clock/location/add/`
2. Codigo: `LOCAL_01`
3. Nombre: `Meriendahaus Principal`
4. IPs permitidas: `["TU_IP_PUBLICA"]`

Opcion B - Via Django Shell:
```bash
python manage.py shell
```
```python
from clock.models import Location

Location.objects.create(
    code="LOCAL_01",
    name="Meriendahaus Principal",
    allowed_ips=["85.123.45.67", "192.168.1.0/24"],
    is_active=True
)
```

### 2. Crear empleados

Desde `/admin/auth/user/add/`:
1. Crear usuario con username y password
2. Agregar nombre y apellido
3. **NO** marcar como staff (staff = administrador)
4. Guardar

### 3. Obtener IP publica del local

Para configurar `allowed_ips`, necesitas la IP publica del router del local.

**Opcion A - Desde el navegador:**
- Visitar https://whatismyip.com
- O visitar https://ifconfig.me
- O visitar https://ipinfo.io

**Opcion B - Desde la terminal:**
```bash
curl ifconfig.me
```

**Opcion C - Alternativas por terminal:**
```bash
curl ipinfo.io/ip
curl icanhazip.com
curl api.ipify.org
```

> **Nota**: La IP publica puede cambiar si el ISP usa IP dinamica. Si los empleados no pueden fichar, verificar si la IP cambio y actualizarla en el admin.

### 4. Generar codigo QR

1. Ir a `/admin/clock/location/`
2. Click en el local
3. Click en "Ver QR" o ir a `/admin/clock/location/1/qr-print/`
4. Imprimir y colocar en lugar visible

---

## Lo que falta para Produccion

### Pendiente

| Item | Prioridad | Descripcion |
|------|-----------|-------------|
| Tests unitarios | Alta | Tests para modelos, vistas, validacion IP |
| Tests integracion | Media | Tests end-to-end del flujo de fichaje |
| Configuracion Nginx | Alta | Reverse proxy + static files |
| HTTPS | Alta | Certificado SSL (Let's Encrypt) |
| Gunicorn/uWSGI | Alta | Servidor WSGI para produccion |
| Backup automatico | Media | Script + cron para backup BD |
| Export Excel/CSV | Baja | Exportar reportes |
| PWA | Baja | Manifest + Service Worker para moviles |
| Notificaciones email | Baja | Alertas de fichajes olvidados |

### Configuracion Nginx (ejemplo)

```nginx
server {
    listen 80;
    server_name tu-dominio.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name tu-dominio.com;

    ssl_certificate /etc/letsencrypt/live/tu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tu-dominio.com/privkey.pem;

    location /static/ {
        alias /path/to/meriendahaus_Zeiterfassung/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Comando collectstatic

```bash
python manage.py collectstatic
```

---

## Uso del Sistema

### Para empleados

1. Conectarse al Wi-Fi del local
2. Abrir navegador en `http://servidor/`
3. Iniciar sesion con usuario/contrasena
4. Escanear QR del local (o escribir codigo)
5. Presionar "Entrada" al llegar
6. Presionar "Salida" al irse

### Para administradores

1. Acceder a `/admin/clock/dashboard/`
2. Ver empleados presentes y estadisticas
3. Revisar alertas de fichajes olvidados
4. Gestionar fichajes en `/admin/clock/timeentry/`
5. Ver reportes de horas semanales/mensuales
6. Cerrar fichajes olvidados si es necesario

---

## Solucion de Problemas

### "No puedes fichar desde fuera del local"

1. Verificar conexion al Wi-Fi del local
2. Comprobar IP publica actual (whatismyip.com)
3. Verificar que esa IP esta en `allowed_ips` del Local
4. Si la IP del ISP cambio, actualizar en admin

### La IP del local cambio

1. Acceder al admin `/admin/clock/location/`
2. Editar el local
3. Actualizar `allowed_ips` con la nueva IP
4. Guardar

### Empleado olvido fichar salida

Opcion A - Admin cierra manualmente:
1. `/admin/clock/timeentry/` → buscar fichaje
2. Editar → agregar hora salida
3. Marcar "Entrada manual" + escribir motivo
4. Guardar

Opcion B - Cierre masivo:
1. `/admin/clock/close-forgotten/`
2. Ver lista de fichajes sin cerrar
3. Confirmar cierre (se cierran a las 23:59 del dia)

### Fichaje duplicado

1. Verificar en historial quien lo creo
2. Eliminar el duplicado desde admin
3. El historial mantiene registro de la eliminacion

---

## Seguridad

### Medidas implementadas

- Validacion de IP para anti-fraude geografico
- CSRF protection en todos los formularios
- Passwords hasheados (PBKDF2 por defecto Django)
- Historial de cambios automatico (audit trail)
- Logging de accesos y fichajes (`zeiterfassung.log`)
- Sesiones seguras con timeout configurable

### Configuracion produccion

En `settings.py` cuando `DEBUG=False`:

```python
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True  # Requiere HTTPS
```

---

## Estructura de Templates

```
templates/
└── admin/
    └── base_site.html              # Template base global (estilos oscuros)

clock/templates/
├── clock/
│   ├── base.html                   # Base para vistas empleados
│   ├── login.html                  # Pantalla login
│   └── clock.html                  # Pantalla fichaje
└── admin/clock/
    ├── admin_base.html             # Base para dashboard (hereda base_site)
    ├── dashboard.html              # Dashboard principal
    ├── who_is_here.html            # Quien esta presente
    ├── hours_summary.html          # Resumen de horas
    ├── employee_detail.html        # Historial empleado
    ├── calendar.html               # Vista calendario
    ├── close_forgotten.html        # Cerrar olvidados
    └── qr_print.html               # Pagina imprimible QR
```

---

## Licencia

Proyecto privado para Meriendahaus.

---

## Historial de Cambios

- **v1.0** - Sistema base con fichaje, validacion IP, panel admin
- **v1.1** - Dashboard personalizado con estadisticas
- **v1.2** - Interfaz oscura estilo GitHub, sidebar menu
