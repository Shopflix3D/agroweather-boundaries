# AgroWeather Live — atualização controlada da malha mundial

## Onde instalar

No repositório **Shopflix3D/agroweather-boundaries** (NÃO na pasta Flutter).
Copie as pastas `.github`, `tools` e `tests` deste pacote para a raiz do repositório.

## O que faz

- Executa **às segundas-feiras, às 04:17 UTC**, ou manualmente em Actions > Update global boundaries > Run workflow.
- Consulta `geoBoundaries gbOpen` (endpoint `ALL/ALL`), que abrange vários países e níveis administrativos.
- Compara `boundaryID` do catálogo atual com `ATTRIBUTION.json` existente.
- Para cada camada modificada, baixa o **GeoJSON simplificado**, verifica a estrutura, coordenadas, anéis e limites de tamanho.
- Atualiza no máximo **12 camadas por execução**, em ordem determinística, evitando cargas enormes e mudanças em massa.
- Atualiza o arquivo de crédito por camada e o horário de geração do manifesto **somente se houve mudanças**.
- Abre uma **pull request para revisão**, SEM substituir automaticamente os dados que os usuários recebem. Os limites cruzados precisam ser revisados visualmente antes do merge.
- A PR mantém histórico de quais camadas mudaram. Não cria diretórios de backup.
- Não apaga países nem níveis não oferecidos na versão atual, não recalcula `world/ADM0.geojson` e não inventa ADM2/municípios.

## Permissões

GitHub > repositório > Settings > Actions > General:
1. Workflow permissions: **Read and write permissions**.
2. Marcar **Allow GitHub Actions to create and approve pull requests**.
3. Salvar.

Se a política da conta não permitir PR automática, o relatório de execução continuará disponível; será necessário habilitar a permissão ou usar um token/autorização compatível.

## Verificação local (Windows)

```powershell
cd D:\Softwares\agroweather-boundaries
python -m unittest discover -s tests -p 'test_*.py' -v
```

Depois do push, ir à aba Actions e executar **Run workflow**.

## Limitações de segurança

Esta primeira automação **não corrige automaticamente cruzamentos topológicos** (por exemplo, fronteiras incorretas no norte do Brasil), porque isso pode alterar limites geográficos oficiais indevidamente. Faz checagens estruturais e deixa diferenças visíveis para revisão humana.

A revisão deve verificar `ATTRIBUTION.json`, inclusive licenças com obrigações adicionais (CC BY-SA, ODbL), antes de publicar novos arquivos. Atribuição sozinha não elimina todas as condições de licença.

## Próximos componentes

- Validação topológica mais profunda das fronteiras compartilhadas (precisa de pipeline geoespacial dedicado).
- Cache por país e nível no Flutter; seleção independente de ADM0, ADM1, ADM2 etc.
- Versionamento e invalidação de cache baseado no `manifest.json`.
- Atualização do index/ajuda com atribuições correspondentes a cada fonte.
