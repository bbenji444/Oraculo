# Guía de acceso al monitor

Para analistas y administradores. Se entra igual que a Oráculo. Diseño técnico en ADR-0043.

## La primera vez (todas las personas)

El administrador te da tu **usuario** y una **contraseña temporal**.

1. Abre el monitor: `http://192.168.0.42:8080` en la oficina, o `http://10.244.214.144:8080` por ZeroTier.
2. Escribe tu usuario y la contraseña temporal.
3. **Crea tu contraseña:** al menos 12 caracteres, con letras y números, y sin tu usuario.
4. **Conecta tu celular:**
   1. abre Microsoft Authenticator;
   2. toca **+** → **Otra cuenta**;
   3. escanea el código QR.
5. Escribe los 6 dígitos que aparecen en la app para «Oráculo Monitor». Listo.

## Los demás días

1. Usuario y contraseña.
2. El código de 6 dígitos de Microsoft Authenticator.
3. Ya no te pide nada hasta que des **«Salir»** (máximo 30 días).

Para cambiar tu contraseña: botón **«Mi contraseña»**, arriba a la derecha.

**Cuida tu cuenta:**
- no compartas tu contraseña;
- no dictes el código de 6 dígitos a nadie: nadie del sistema te lo va a pedir;
- si cambias de celular, avísale al administrador.

## Qué ve cada quien

| | Usuario | Superusuario |
|---|---|---|
| Explorar, Casos, Historial | Sí; en Historial, solo sus búsquedas | Sí; en Historial, las suyas, las automáticas y «Ver de todos» |
| Conceptos | Los ve y los prueba | Los crea y los cambia |
| Envíos, Estado del sistema, Accesos | No | Sí |

Las búsquedas de otra persona no existen para ti: la base de datos no las entrega (seguridad por filas).

## Para administrar (superusuarios), pestaña «Accesos»

- **Dar de alta a alguien:** «+ Nueva persona» con usuario sin espacios (`ana.lopez`), nombre y rol.
  - Aparece su **contraseña temporal una sola vez**: cópiala y entrégala en persona.
- **Olvidó su contraseña:** «Editar» → **Restablecer contraseña**. Le sale una temporal nueva y sus sesiones se cierran.
- **Cambió o perdió el celular:** «Editar» → **Reiniciar autenticador**. Al entrar escanea un QR nuevo.
- **Quitarle el acceso un tiempo:** «Editar» → apaga «Puede entrar».
- **Borrarla:** «Editar» → **Borrar persona**. Desaparece de la lista y ya no puede entrar. Sus búsquedas y la bitácora se quedan, y su usuario no se puede volver a usar (así nadie nuevo ve lo suyo).
- **Cambiar su rol:** «Editar» → Rol.

**Etiquetas junto a cada persona:**
- **«Contraseña temporal»:** todavía no entra por primera vez.
- **«Sin Authenticator»:** no ha conectado su celular.
- **«Bloqueada hasta…»:** falló 5 veces seguidas. Se desbloquea sola a los 15 minutos.

**«Llaves de sistema»** son para que otros programas consulten el monitor (como las llaves de la API de ChatGPT). Las personas no las usan para entrar.

**El sistema no deja:**
- quitarte tu propio rol ni desactivarte;
- quedarse sin superusuario.

## Si el superusuario no puede entrar

Entra al servidor por SSH, con el usuario `noticias`, y corre:

```bash
cd ~/monitor-noticias && make acceso ARGS="--usuario benji"
```

Te da una contraseña temporal que se ve una sola vez. Si además cambiaste de celular, agrega `--reiniciar-codigo` para escanear un QR nuevo.
