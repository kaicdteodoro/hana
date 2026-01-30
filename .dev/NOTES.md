# hana — Development Notes

## Status Atual
- [x] Implementação core completa
- [x] Testes passando (37/37)
- [x] Docker environment configurado
- [ ] Testes de integração com WordPress real
- [ ] ACF plugin integration (campo repeater/gallery)

## Próximos Passos

### Prioridade Alta
1. **Testar com WordPress real**
   - Subir ambiente: `make up && make setup`
   - Configurar `hana.yaml` com app_password gerado
   - Testar: `make health` → `make dry-run` → `make run`

2. **ACF Integration**
   - O setup.sh cria CPT mas não instala ACF
   - Campos ACF precisam ser criados manualmente ou via código
   - Verificar payload correto para repeater (`cores_disponiveis`) e gallery (`imagens`)

3. **Validar dedup de mídia**
   - Testar `checksum_meta` strategy com uploads reais
   - Confirmar que meta query funciona no endpoint `/wp-json/wp/v2/media`

### Prioridade Média
4. **Retry logic**
   - Implementar retry com backoff no `wordpress.py`
   - Atualmente só detecta `TransportError.retryable`, não re-executa

5. **Parallel execution**
   - `parallel_skus > 1` usa ThreadPoolExecutor
   - Testar se locking funciona corretamente em paralelo
   - Verificar ordenação determinística do output

6. **Ledger rebuild**
   - `corruption_policy: rebuild` declarado mas não implementado
   - Requer query de todos os SKUs do WordPress

### Prioridade Baixa
7. **CLI improvements**
   - `hana status` — mostrar estado do ledger
   - `hana retry-incomplete` — reprocessar SKUs incompletos
   - `hana compact-ledger` — compactar ledger

8. **Observability**
   - Métricas (requests/s, errors, latency)
   - Prometheus endpoint opcional

## Decisões de Design

### Por que não WooCommerce?
O sistema usa CPT `produtos` customizado, não `product` do WooCommerce.
Se precisar WooCommerce, alterar:
- `PRODUTOS_ENDPOINT` → `/wp-json/wc/v3/products`
- Autenticação → OAuth ou Consumer Key/Secret
- Payload → formato WooCommerce

### Por que filesystem lock?
- Simples e funciona em single-node
- Advisory lock (fcntl) é alternativa para multi-process
- Para multi-node, precisaria Redis/DB lock

### Por que não async/aiohttp?
- `requests` é síncrono mas suficiente para o caso de uso
- Rate limiting já serializa requests
- Complexidade adicional não justificada

## Configurações Importantes

### WordPress
- Permalinks DEVEM estar em "Post name" (não "Plain")
- REST API deve estar habilitada
- Application Passwords requer HTTPS em produção (ou filtro para permitir HTTP)

### ACF
- Versão PRO necessária para campos repeater/gallery via REST
- Ou usar ACF to REST API plugin

## Arquivos Chave
```
hana/engine.py      # Lógica principal — começar aqui para entender o fluxo
hana/wordpress.py   # Cliente REST — ajustar endpoints aqui
hana/config.py      # Todas as opções — referência completa
```

## Comandos Úteis
```bash
make up              # Subir WordPress + MariaDB
make setup           # Configurar WordPress (CPT, taxonomy, app password)
make health          # Testar conexão
make dry-run         # Simular ingestão
make run             # Executar ingestão
make test            # Rodar testes
make logs            # Ver logs dos containers
make clean           # Limpar tudo
```
