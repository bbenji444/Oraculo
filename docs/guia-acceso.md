# Guía de acceso al monitor (llaves de Oráculo)

Para analistas y administradores. Diseño técnico en ADR-0042.

## Para entrar (todas las personas)

1. Abre el monitor (`http://10.244.214.144:8080` por ZeroTier o `http://192.168.0.42:8080` en la oficina).
2. Pega tu llave en «Entrar con tu llave». Empieza con `orc_live_` y mide 58 caracteres.
3. Listo. La sesión dura hasta 8 horas y se cierra sola tras 1 hora sin uso. Para salir antes, usa «Salir» (arriba a la derecha).

**Cuida tu llave como una contraseña:**

- no la pegues en chats, correos ni documentos;
- si crees que alguien la vio, pide que la revoquen y te den otra;
- guárdala en un gestor de contraseñas, no en un archivo de texto en el escritorio.

## Qué ve cada quien

| | Usuario | Superusuario |
|---|---|---|
| Explorar, Casos, Historial | Sí; en Historial, solo sus búsquedas | Sí; en Historial, las suyas y las automáticas, y «Ver de todos» |
| Conceptos | Los ve y los prueba | Los crea y los cambia |
| Envíos, Estado del sistema, Accesos | No | Sí |

Las búsquedas de otra persona no existen para ti: la base de datos no las entrega (seguridad por filas).

## Para administrar (superusuarios), pestaña «Accesos»

- **Dar de alta a alguien:** «+ Nueva persona» → usuario sin espacios (`ana.lopez`), nombre, correo opcional y rol.
- **Darle su llave:** «Llaves» → «+ Nueva llave».
  - Elige vigencia: 90 días es lo recomendado.
  - La llave aparece **una sola vez**: cópiala y entrégala en persona o por un canal seguro.
- **Revocar:** «Llaves» → «Revocar». Deja de servir al instante y la sesión de esa persona se cierra.
- **Quitar el acceso a alguien:** «Editar» → apaga «Puede entrar». Todas sus llaves dejan de servir.
- **Cambiar rol:** «Editar» → Rol.

El sistema no deja:

- quitarte tu propio rol ni desactivarte;
- quedarse sin superusuario;
- revocar tu única llave vigente (crea otra antes).

## Si se pierde la llave del superusuario

En el servidor, por SSH, con el usuario `noticias`:

```bash
cd ~/monitor-noticias && make crear-llave ARGS="--usuario benji --dias 365"
```

La llave sale una vez en la pantalla de la terminal. Después entra y revoca la vieja en «Accesos».
