# Procedencia: hashes de commit originales y reescritos

Antes de publicar el repositorio se reescribió el historial para reemplazar **solo** el email
de autor y de committer de los 11 commits. Se conservaron sin cambios el nombre del autor,
los mensajes, las fechas, el orden, los padres y el contenido de cada commit.

Cambiar el email cambia el hash del commit. El hash del árbol (*tree*) solo depende del
contenido de los archivos, así que es idéntico antes y después. Se verificó commit por commit.

## Correspondencia

| # | Commit original | Commit publicado | Tree (idéntico en ambos) | Mensaje |
|---|---|---|---|---|
| 1 | `25a09509e2050074d249c8ac2f4bc1f2b7a5e1fe` | `e7d453bf1ee5ebc82c657a7a5bc5fc6d5d8e94f2` | `b18ad0918acc476f6d587c386c01bbfa46ccf6ff` | Etapa 1: evaluación de retrieval A (dense) vs B (hybrid RRF) |
| 2 | `874060ea130edbe2ef1ec335cd2ed70108fd6ece` | `ceeaed856ec4f007b60e1171f078c734a338bcd2` | `e905dd5e8a5ad7e377818108093cc47a0b5f885d` | Etapa 2: pipeline de generación con citas y abstención (offline) |
| 3 | `5e3b8d83b443cdc22d22dc16c0f7b4a67cf20f68` | `f69798655e0e0b6dd23209582fae4408604dc62a` | `ccda8cb7acc9c1690778667d00c893e24f6064e7` | gen-check online con datos del modelo; registrar encabezados de rate limit |
| 4 | `3d3a31c79c6b61261d86d5b22ace27788e61ac97` | `e6de8139260e1e5d409908d24d071cd58c4f18cf` | `cbd476acce52c95d92077d3330e4620c05a4e42b` | Limitador y presupuesto conservadores para el benchmark online |
| 5 | `4986eddde7d4db40b2e9ce63ed7e5b70abc1e25a` | `df6981a54d65e1975ce0c41a8190a8eadffef01c` | `8d6790ec7e7890572a941ef893655c52a0a84941` | Cierre de Etapa 2: reporte, artefactos del benchmark Groq A/B y verificación |
| 6 | `a222dbb32594be4d8f42c493aef8d2c3d295c3ab` | `d4b18bc036d8bf483284b83904840c37f2a40013` | `2d1bbcee670947bf3ddf3f08f11e019862af1e16` | Etapa 3A: faithfulness por afirmación offline (sin llamadas a modelos) |
| 7 | `65acc951453f42524a44c55e0180363b13459c49` | `c7a9f68f8d2d0e062c6477f73b1be0936af1580b` | `e99b08007371739188a88bf03e676b6c60a9e0b5` | Etapa 3A: cierre de la anotación humana (ronda 1) y controles de perturbación |
| 8 | `c2fb189ae0f55b0e7e0dd5cca855b964c1f74d89` | `0f98d3983a7c67315fc91d5fa230497dfc7c9134` | `c3b295d20f8333b579271ef148ab4e8d96849780` | Versionar la planilla anotada byte a byte para preservar su sha256 |
| 9 | `7094fa00bed8f9613c168c067cfe3ad9196aece0` | `a750ab375d4ac118951378c92802a1f2bdcd795e` | `b9ad213e5f778cb2ca5d4bb8172a060dab51f520` | Etapa 3B: juez semántico judge-v1 (qwen/qwen3.8-27b) y smoke de 8 casos |
| 10 | `a3c90db11d2cefc3ae52390ee773529f290336ee` | `74cba447ed583a2592474e6dcd71905b1d6527bc` | `7e40ebc8662b23d8a3e0fb4356b997a7c986cffb` | Cierre de Etapa 3B: evaluación completa de judge-v1-otpm (47 casos) y auditoría |
| 11 | `987bebceffc85e63288ff18bccccb6e70e48ec7d` | `0da22c438c5c7f2420a8091727dc5c50f61bda44` | `40ca336a5ef51dc1b3034bc06ea29e86344ffe27` | Etapa 4A: dashboard Streamlit local de solo lectura |

## Por qué los manifiestos conservan los hashes originales

Cada corrida guardó en su manifiesto el campo `git_commit`, el commit del código con el que
se ejecutó. Los manifiestos son artefactos experimentales y no se modificaron después de la
reescritura, así que siguen mostrando el hash **original**:

| Manifiesto | `git_commit` original | Commit publicado equivalente |
|---|---|---|
| `runs/eval/{A_dense_k5,B_hybrid_k5}/gen/fake_extractive/gen_manifest.json` | `25a0950…` | `e7d453b…` |
| `runs/smoke/{calibration_A,eval_A}/gen_manifest.json` | `874060e…` | `ceeaed8…` |
| `runs/eval/{A_dense_k5,B_hybrid_k5}/gen/groq_gpt-oss-120b/gen_manifest.json` | `3d3a31c…` | `e6de813…` |
| `runs/stage3/judge/smoke_qwen3.8-27b/judge_manifest.json` | `c2fb189…` | `0f98d39…` |
| `runs/stage3/judge/{full,judge-v1-otpm}_qwen3.8-27b/judge_manifest.json` | `7094fa0…` | `a750ab3…` |

La referencia al commit `a222dbb` en [`faithfulness.md`](faithfulness.md) corresponde al commit
publicado `d4b18bc`.

## Cómo verificar la equivalencia

En un clon del repositorio publicado, para cada fila de la tabla de correspondencia:

```bash
git rev-parse <commit_publicado>^{tree}   # debe dar el tree de la tabla
git log -1 --format='%an %aI %s' <commit_publicado>
```

Si el tree coincide, el commit publicado tiene exactamente los mismos archivos, byte a byte,
que el commit original registrado en el manifiesto. Para revisar el código con el que se generó
una corrida, hay que hacer checkout del commit publicado equivalente.

## Limitación

Los commits originales no se publican, así que no se puede contrastar públicamente la autoría
ni los demás metadatos originales. Esta tabla es una declaración del autor.

Lo que sí se puede verificar es el contenido. Los hashes de tree de la tabla identifican de
forma criptográfica los archivos de cada commit, y son los mismos que tienen los commits
publicados. Lo que no se puede probar con el repositorio publicado es que un hash original
haya tenido exactamente ese tree.
