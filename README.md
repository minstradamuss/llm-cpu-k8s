# CPU-only vLLM в Minikube

Тестовое задание для команды исследования технологий машинного обучения.

## Что используется

- vLLM 0.32.0 в официальном CPU-образе `vllm/vllm-openai-cpu:v0.32.0-x86_64`.
- Модель `Qwen/Qwen2.5-0.5B-Instruct` на CPU, `float32`, контекст 1024 токена.
- Kubernetes ConfigMap, Secret, PVC, Deployment и Service.
- Контейнер под UID 10001, без root, без GPU, с ограниченными правами.

Для запуска нужны Docker, Minikube, kubectl и примерно 4 CPU / 12 ГиБ RAM. Сборка рассчитана на x86_64. На некоторых CPU инструкции AVX могут ограничивать совместимость официального образа.

## Запуск

```bash
minikube start --cpus=4 --memory=12288 --disk-size=25g
minikube image build -t llm-cpu:0.1 .
```

Создайте ресурс Secret с реальным ключом. Не коммитьте ключ в git. Один из способов — создать локальный файл `.env` (он добавлен в `.gitignore`):

```text
HF_TOKEN=
API_TOKEN=YOUR_RANDOM_LONG_TOKEN
```

Для публичной модели HF_TOKEN может быть пустым. Для gated-моделей нужен настоящий токен HF.

```bash
kubectl create secret generic llm-secrets --from-env-file=.env
kubectl apply -k k8s/
kubectl get pods -w
```

Первый запуск скачивает модель в PVC. При рестарте initContainer читает файл `.ready.json` и не обращается к Hugging Face. Основной контейнер работает с `HF_HUB_OFFLINE=1` и читает volume без права записи.

```bash
kubectl logs deployment/llm-cpu -c download-model
kubectl logs deployment/llm-cpu -c vllm
kubectl port-forward service/llm-cpu 8000:8000
```

В другом терминале выполните запрос (Linux/macOS/PowerShell с curl.exe):

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_RANDOM_LONG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-cpu","messages":[{"role":"user","content":"Привет!"}],"max_tokens":32}'
```

Запрос без токена должен вернуть HTTP 401.

## Конфигурация и безопасность

Параметры модели и запуска лежат в `k8s/configmap.yaml`. После изменения ConfigMap примените манифесты и перезапустите Deployment:

```bash
kubectl apply -k k8s/
kubectl rollout restart deployment/llm-cpu
```

`SafeRequestsMiddleware` в `scripts/safe_requests.py` проверяет `Authorization: Bearer ...` для всех HTTP endpoints, кроме `/health` и `/ping`. Это важно, потому что встроенный `--api-key` vLLM покрывает не все маршруты. Также он регистрирует факт запроса: метод, тип маршрута, HTTP-код и задержку. Тексты промптов, ответы и сами токены в журнал не попадают.

У vLLM отключены логи запросов, ответов и Uvicorn access log. Дополнительно файл `logging.json` устанавливает уровни для внутренних логгеров. Класс middleware также не выводит строку запроса или заголовки.

Рекомендуется использовать этот сервис только через `kubectl port-forward` или внутри закрытого кластера. Для публичного доступа потребуется TLS, сетевые политики, rate limiting и регулярная ротация токенов. `/health` оставлен открытым для Kubernetes probes.

## Зависимости

Используется официальный CPU-образ строго заданной версии vLLM. Список Python-пакетов и **всех транзитивных зависимостей** фиксируется командой `pip freeze --all` в `/opt/app/requirements.txt` при сборке собственного Docker-образа. В репозитории `requirements.txt` сначала содержит только прямую версию vLLM. Перед окончательной отправкой в GitHub нужно сохранить полный lock из собранного образа:

```bash
kubectl exec deployment/llm-cpu -c vllm -- cat /opt/app/requirements.txt > requirements.txt
```

Эта команда выполняется после запуска пода. После экспорта `requirements.txt` с транзитивными пакетами закоммитьте его вместе с остальными файлами. Эта операция необходима для полного выполнения требования о pinned dependencies. Для строгой повторяемости сборки также можно закрепить исходный Docker-образ по digest.

## Нагрузочный тест (дополнительно)

После запуска сервиса:

```bash
export API_TOKEN=YOUR_RANDOM_LONG_TOKEN
python scripts/benchmark.py --samples 3
```

Скрипт отдельно проверяет короткий и длинный промпты и печатает таблицу медианных TTFT, E2E latency и throughput (токенов/с). Для потокового ответа время первого содержательного токена определяется по SSE, а число токенов — из `usage.completion_tokens`.

| Промпт | TTFT, с | Latency, с | Throughput, токен/с |
|---|---:|---:|---:|
| Короткий | — | — | — |
| Длинный | — | — | — |

Результаты не заполнены, поскольку запуск в Minikube на реальном CPU не проводился.

Для большого количества коротких запросов можно экспериментировать с `max_num_seqs`, пакетированием и количеством потоков CPU. Для небольшого количества запросов с длинным контекстом стоит проверять `max_model_len`, доступный размер KV cache и `max_num_batched_tokens`. Каждое изменение нужно оценивать на одинаковой нагрузке по TTFT, задержке и пропускной способности.

## Проверка кода без Kubernetes

```bash
python -m unittest discover -s tests -v
```

Документация: https://docs.vllm.ai/en/v0.32.0/getting_started/installation/cpu/ ; https://docs.vllm.ai/en/v0.32.0/cli/serve/ ; https://docs.vllm.ai/en/v0.32.0/examples/features/logging_configuration/
