# Issue tracker: GitHub

Los issues y especificaciones de este proyecto se administran mediante GitHub Issues:

- Repositorio: `Mauricio-Bustos-DrSimi/FactibilidadGDP`
- Remoto: `https://github.com/Mauricio-Bustos-DrSimi/FactibilidadGDP.git`
- Cliente: GitHub CLI (`gh`)

## Requisito local

Antes de operar con Issues:

```bash
gh auth status
```

Si GitHub CLI no está instalado o autenticado, detener la operación y solicitar su configuración. No sustituir silenciosamente GitHub Issues por archivos locales.

## Operaciones

- Crear: `gh issue create --title "..." --body-file <archivo>`
- Consultar: `gh issue view <número> --comments`
- Listar: `gh issue list --state open`
- Comentar: `gh issue comment <número> --body "..."`
- Cerrar: `gh issue close <número> --comment "..."`
- Asignar: `gh issue edit <número> --add-assignee @me`

GitHub CLI debe inferir el repositorio desde `git remote -v`.

## Publicación y lectura

Cuando una skill indique “publicar en el issue tracker”, debe crear un GitHub Issue.

Cuando una skill solicite “obtener el ticket”, debe leer el Issue, sus comentarios, etiquetas y relaciones de bloqueo.

## Dependencias

Usar las dependencias nativas de GitHub Issues cuando estén disponibles. Si no lo están, indicar al comienzo del cuerpo:

```text
Blocked by: #<número>, #<número>
```

Un ticket solo está disponible cuando todos sus bloqueadores están cerrados.

## Pull requests como solicitudes

**PRs as a request surface: no.**

Los Pull Requests no ingresan automáticamente al flujo de solicitudes o triage.
