# Ingar – Software de Acceso Remoto

**Ingar** es un proyecto de software de acceso remoto de código abierto, similar en funcionalidades a TeamViewer.  
Permite controlar escritorios de forma remota a través de una conexión WebSocket cifrada.

---

## Características

| Funcionalidad | Descripción |
|---|---|
| **Control remoto** | Captura la pantalla del equipo remoto y reenvía eventos de ratón y teclado |
| **ID único** | Cada cliente recibe un ID de 9 dígitos (ej. `123 456 789`) |
| **Contraseña de sesión** | Autenticación por contraseña aleatoria generada al iniciar |
| **Chat en tiempo real** | Mensajería instantánea durante la sesión |
| **Transferencia de archivos** | Envío de archivos al equipo remoto por fragmentos |
| **Cifrado AES-256-GCM** | Módulo de cifrado disponible para futuras extensiones P2P |
| **GUI intuitiva** | Interfaz gráfica con tkinter inspirada en TeamViewer |

---

## Arquitectura

```
ingar/
├── server/
│   └── signaling_server.py   # Servidor WebSocket de señalización y relay
├── client/
│   ├── main.py               # Punto de entrada del cliente
│   ├── core/
│   │   ├── connection.py     # Gestor de conexión WebSocket
│   │   ├── screen_capture.py # Captura de pantalla (mss + Pillow)
│   │   ├── input_handler.py  # Inyección y captura de eventos (pynput)
│   │   ├── file_transfer.py  # Transferencia de archivos por fragmentos
│   │   └── crypto.py         # Cifrado AES-256-GCM
│   └── gui/
│       ├── main_window.py    # Ventana principal
│       ├── remote_view.py    # Visor de escritorio remoto
│       └── chat_window.py    # Ventana de chat
├── shared/
│   └── protocol.py           # Tipos de mensajes y utilidades
├── run_server.py             # Lanzador del servidor
├── run_client.py             # Lanzador del cliente
└── requirements.txt
```

### Flujo de conexión

```
Cliente A                     Servidor                      Cliente B
   |                             |                             |
   |------- register_ack ------->|                             |
   |                             |<------ register_ack --------|
   |                             |                             |
   |-- connect_request (ID+pw) ->|-- connect_request (from A)->|
   |                             |                             | (acepta)
   |<------- connect_accept -----|<------ connect_accept ------|
   |                             |                             |
   |<======= screen_frame =============================== relay|
   |======== input_event ============================ relay ==>|
   |<======= chat_message ============================= relay  |
```

---

## Instalación

```bash
git clone https://github.com/maxibalzarini/ingar.git
cd ingar
pip install -r requirements.txt
```

### Dependencias

- `websockets` – comunicación WebSocket
- `mss` – captura de pantalla de alta velocidad
- `Pillow` – procesamiento de imágenes y compresión JPEG
- `pynput` – captura e inyección de eventos de ratón/teclado
- `cryptography` – cifrado AES-256-GCM

---

## Uso

### 1. Iniciar el servidor

```bash
python run_server.py
# Por defecto escucha en ws://0.0.0.0:8765

# Opciones:
python run_server.py --host 0.0.0.0 --port 8765
```

### 2. Iniciar el cliente

```bash
python run_client.py
# Conecta a ws://localhost:8765 por defecto

# Servidor remoto:
python run_client.py --server ws://mi-servidor.com:8765
```

### 3. Conectar dos equipos

1. En el **equipo a controlar**: Inicia el cliente → anota el **ID** y la **Contraseña**.
2. En el **equipo controlador**: Inicia el cliente → ingresa el ID y la contraseña → pulsa **Conectar**.
3. El equipo controlado mostrará un diálogo de confirmación.
4. Una vez aceptado, se abre la ventana de **Control Remoto**.

### 4. Capturar entrada en la ventana remota

En la ventana de Control Remoto, activa la casilla **"Capturar entrada"** para que los eventos del ratón y el teclado se envíen al equipo remoto.

---

## Opciones de la ventana remota

- **Calidad**: Baja / Media / Alta (afecta la compresión JPEG)
- **Chat**: Mensajería instantánea con el par
- **Enviar archivo**: Transferencia de archivos durante la sesión
- **Terminar sesión**: Cierra la conexión

---

## Consideraciones de seguridad

- Las contraseñas se almacenan en el servidor **sólo como hash SHA-256**.
- El módulo `crypto.py` implementa **AES-256-GCM** para cifrado de extremo a extremo, extensible a conexiones P2P futuras.
- Para producción se recomienda ejecutar el servidor detrás de un proxy TLS (nginx + certificado SSL).

---

## Licencia

MIT – Uso libre para proyectos personales y comerciales.
