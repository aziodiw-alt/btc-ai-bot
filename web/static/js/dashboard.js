(async function initializeDashboardChart() {
    const chartElement = document.getElementById("btc-chart");
    const loadingElement = document.getElementById("chart-loading");
    const timeframeLabel = document.getElementById("chart-timeframe-label");
    const priceElement = document.getElementById("btc-price");
    const updateStatusElement = document.getElementById("chart-update-status");
    const liveStatusElement = updateStatusElement
        ? updateStatusElement.closest(".live-status")
        : null;
    const timeframeButtons = Array.from(
        document.querySelectorAll(".timeframe-button")
    );

    if (!chartElement) {
        return;
    }

    const activeSymbol = chartElement.dataset.symbol || "BTCUSDT";
    const activeExchange = chartElement.dataset.exchange || "bybit";
    const priceDigits = activeSymbol === "BTCUSDT" ? 1 : 2;

    function showLoading(message = "Загружаем свечи и уровни…") {
        if (!loadingElement) {
            return;
        }

        loadingElement.textContent = message;
        loadingElement.classList.remove("is-error");
        loadingElement.hidden = false;
    }

    function hideLoading() {
        if (loadingElement) {
            loadingElement.hidden = true;
        }
    }

    function showError(message) {
        if (!loadingElement) {
            return;
        }

        loadingElement.textContent = message;
        loadingElement.classList.add("is-error");
        loadingElement.hidden = false;
    }

    function disableButtons(disabled) {
        timeframeButtons.forEach((button) => {
            button.disabled = disabled;
        });
    }

    if (typeof LightweightCharts === "undefined") {
        showError("Не удалось загрузить библиотеку графика.");
        return;
    }

    const chart = LightweightCharts.createChart(chartElement, {
        width: chartElement.clientWidth,
        height: chartElement.clientHeight,
        layout: {
            background: { color: "#1f2937" },
            textColor: "#9ca3af"
        },
        grid: {
            vertLines: { color: "rgba(75, 85, 99, 0.24)" },
            horzLines: { color: "rgba(75, 85, 99, 0.24)" }
        },
        rightPriceScale: {
            borderColor: "#374151",
            scaleMargins: { top: 0.12, bottom: 0.12 }
        },
        timeScale: {
            borderColor: "#374151",
            timeVisible: true,
            secondsVisible: false,
            rightOffset: 6
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal
        },
        localization: {
            locale: "ru-RU",
            priceFormatter: (price) => price.toLocaleString("ru-RU", {
                minimumFractionDigits: priceDigits,
                maximumFractionDigits: priceDigits
            })
        }
    });

    const candles = chart.addCandlestickSeries({
        upColor: "#34d399",
        downColor: "#f87171",
        borderVisible: false,
        wickUpColor: "#34d399",
        wickDownColor: "#f87171",
        priceLineVisible: false
    });

    const zones = [];
    let levelsInitialized = false;
    const levelPriceLines = [];
    let currentPriceLine = null;
    let currentRequestId = 0;
    let activeTimeframe = "240";
    let activeTimeframeLabel = "4H";
    function addPriceLine(price, color, title, lineStyle) {
        const numericPrice = Number(price);

        if (!Number.isFinite(numericPrice)) {
            return null;
        }

        return candles.createPriceLine({
            price: numericPrice,
            color,
            lineWidth: 1,
            lineStyle,
            axisLabelVisible: true,
            title
        });
    }

    function normalizeZone(value, fallbackWidthPct = 0.0025) {
        if (Array.isArray(value) && value.length >= 2) {
            const first = Number(value[0]);
            const second = Number(value[1]);

            if (Number.isFinite(first) && Number.isFinite(second)) {
                return {
                    low: Math.min(first, second),
                    high: Math.max(first, second)
                };
            }
        }

        const center = Number(value);

        if (!Number.isFinite(center)) {
            return null;
        }

        return {
            low: center * (1 - fallbackWidthPct),
            high: center * (1 + fallbackWidthPct)
        };
    }

    function createZone(value, className, label) {
        const zone = normalizeZone(value);

        if (!zone) {
            return;
        }

        const element = document.createElement("div");
        const caption = document.createElement("span");

        element.className = `chart-zone ${className}`;
        caption.textContent = label;
        element.appendChild(caption);
        chartElement.parentElement.appendChild(element);

        zones.push({ ...zone, element });
    }

    function initializeLevels(levels) {
        if (levelsInitialized) {
            zones.forEach(({ element }) => element.remove());
            zones.length = 0;
            levelPriceLines.forEach((line) => candles.removePriceLine(line));
            levelPriceLines.length = 0;
        }

        currentPriceLine = addPriceLine(
            levels.current_price,
            "#60a5fa",
            "Цена",
            LightweightCharts.LineStyle.Solid
        );
        levelPriceLines.push(currentPriceLine);
        levelPriceLines.push(addPriceLine(
            levels.stop_loss,
            "#ef4444",
            "Stop",
            LightweightCharts.LineStyle.Dashed
        ));
        levelPriceLines.push(addPriceLine(
            levels.take_profit_1,
            "#fbbf24",
            "TP1",
            LightweightCharts.LineStyle.Dashed
        ));
        levelPriceLines.push(addPriceLine(
            levels.take_profit_2,
            "#f59e0b",
            "TP2",
            LightweightCharts.LineStyle.Dashed
        ));

        createZone(
            levels.support_zone || levels.support,
            "zone-support",
            "Поддержка / Buy Zone 1"
        );
        createZone(levels.resistance, "zone-resistance", "Сопротивление");
        createZone(levels.buy_zone_2, "zone-buy", "Buy Zone 2");

        levelsInitialized = true;
    }

    function updateCurrentPrice(payload) {
        const currentPrice = Number(payload.levels.current_price);

        if (!Number.isFinite(currentPrice)) {
            return;
        }

        if (priceElement) {
            priceElement.textContent = currentPrice.toLocaleString("ru-RU", {
                minimumFractionDigits: priceDigits,
                maximumFractionDigits: priceDigits
            });
        }

        if (currentPriceLine) {
            currentPriceLine.applyOptions({ price: currentPrice });
        }
    }

    function formatLevel(value) {
        return Number(value).toLocaleString("ru-RU", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        });
    }

    function updateLevelCards(levels) {
        const values = {
            "buy-zone-1": `${formatLevel(levels.buy_zone_1[0])} – ${formatLevel(levels.buy_zone_1[1])}`,
            "buy-zone-2": `${formatLevel(levels.buy_zone_2[0])} – ${formatLevel(levels.buy_zone_2[1])}`,
            "stop-loss": formatLevel(levels.stop_loss),
            "take-profit-1": formatLevel(levels.take_profit_1),
            "take-profit-2": formatLevel(levels.take_profit_2)
        };

        Object.entries(values).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });

        const averages = {
            "buy-zone-1-average": (
                Number(levels.buy_zone_1[0])
                + Number(levels.buy_zone_1[1])
            ) / 2,
            "buy-zone-2-average": (
                Number(levels.buy_zone_2[0])
                + Number(levels.buy_zone_2[1])
            ) / 2
        };

        Object.entries(averages).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = formatLevel(value);
            }
        });
    }

    function updateLegend(levels) {
        const values = {
            "legend-support": (
                `Поддержка / Buy Zone 1: ${formatLevel(levels.buy_zone_1[0])}`
                + ` – ${formatLevel(levels.buy_zone_1[1])}`
            ),
            "legend-resistance": (
                `Сопротивление: ${formatLevel(levels.resistance)}`
            ),
            "legend-buy-zone-2": (
                `Buy Zone 2: ${formatLevel(levels.buy_zone_2[0])}`
                + ` – ${formatLevel(levels.buy_zone_2[1])}`
            ),
            "legend-targets": (
                `SL ${formatLevel(levels.stop_loss)}`
                + ` · TP1 ${formatLevel(levels.take_profit_1)}`
                + ` · TP2 ${formatLevel(levels.take_profit_2)}`
            )
        };

        Object.entries(values).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
    }

    function setUpdateStatus(message, state = "ready") {
        if (!updateStatusElement || !liveStatusElement) {
            return;
        }

        updateStatusElement.textContent = message;
        liveStatusElement.classList.toggle("is-updating", state === "updating");
        liveStatusElement.classList.toggle("is-error", state === "error");
    }

    function formatUpdateTime() {
        return new Intl.DateTimeFormat("ru-RU", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        }).format(new Date());
    }

    function positionZones() {
        zones.forEach((zone) => {
            const highY = candles.priceToCoordinate(zone.high);
            const lowY = candles.priceToCoordinate(zone.low);

            if (highY === null || lowY === null) {
                zone.element.hidden = true;
                return;
            }

            zone.element.hidden = false;
            zone.element.style.top = `${Math.min(highY, lowY)}px`;
            zone.element.style.height = `${Math.max(2, Math.abs(lowY - highY))}px`;
        });
    }

    let zonePositionFrame = null;

    function scheduleZonePositioning(extraFrame = false) {
        if (zonePositionFrame !== null) {
            window.cancelAnimationFrame(zonePositionFrame);
        }

        zonePositionFrame = window.requestAnimationFrame(() => {
            zonePositionFrame = null;
            positionZones();

            // Lightweight Charts sometimes applies a new vertical price scale
            // one frame after wheel/drag interaction.
            if (extraFrame) {
                window.requestAnimationFrame(positionZones);
            }
        });
    }

    function setActiveTimeframe(timeframe, label) {
        timeframeButtons.forEach((button) => {
            button.classList.toggle(
                "is-active",
                button.dataset.timeframe === timeframe
            );
        });

        if (timeframeLabel) {
            timeframeLabel.textContent = label;
        }

        activeTimeframe = timeframe;
        activeTimeframeLabel = label;
    }

    async function loadTimeframe(
        timeframe,
        label,
        { silent = false, fitContent = true } = {}
    ) {
        const requestId = ++currentRequestId;

        if (silent) {
            setUpdateStatus("Обновляем данные…", "updating");
        } else {
            showLoading(`Загружаем график ${label}…`);
            disableButtons(true);
        }

        try {
            const apiUrl = new URL(
                chartElement.dataset.apiUrl,
                window.location.origin
            );
            apiUrl.searchParams.set("timeframe", timeframe);
            apiUrl.searchParams.set("symbol", activeSymbol);
            apiUrl.searchParams.set("exchange", activeExchange);
            apiUrl.searchParams.set(
                "strategy",
                chartElement.dataset.strategy || "swing"
            );

            const response = await fetch(apiUrl, {
                headers: { Accept: "application/json" }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const payload = await response.json();

            if (requestId !== currentRequestId) {
                return;
            }

            if (!payload.candles || payload.candles.length === 0) {
                throw new Error(
                    `${activeExchange.toUpperCase()} не вернул свечи`
                );
            }

            candles.setData(payload.candles);
            initializeLevels(payload.levels);
            updateCurrentPrice(payload);
            updateLevelCards(payload.levels);
            updateLegend(payload.levels);
            setActiveTimeframe(
                payload.timeframe || timeframe,
                payload.timeframe_label || label
            );

            chart.applyOptions({
                timeScale: {
                    timeVisible: timeframe !== "D",
                    secondsVisible: false
                }
            });
            if (fitContent) {
                chart.timeScale().fitContent();
            }

            scheduleZonePositioning(true);

            if (!silent) {
                hideLoading();
            }

            setUpdateStatus(`Обновлено в ${formatUpdateTime()}`);
        } catch (error) {
            console.error(error);

            if (silent) {
                setUpdateStatus(
                    "Автообновление не удалось. Повторим через 30 сек.",
                    "error"
                );
            } else {
                showError("Не удалось получить данные графика. Проверьте соединение с Bybit.");
            }
        } finally {
            if (!silent && requestId === currentRequestId) {
                disableButtons(false);
            }
        }
    }

    timeframeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (button.classList.contains("is-active")) {
                return;
            }

            loadTimeframe(
                button.dataset.timeframe,
                button.dataset.label
            );
        });
    });

    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
        scheduleZonePositioning(true);
    });

    // The HTML zones live above the chart canvas. Recalculate their vertical
    // coordinates whenever the user changes either the time or price scale.
    chartElement.addEventListener(
        "wheel",
        () => scheduleZonePositioning(true),
        { passive: true }
    );
    chartElement.addEventListener(
        "pointermove",
        () => scheduleZonePositioning(true),
        { passive: true }
    );
    chartElement.addEventListener(
        "pointerup",
        () => scheduleZonePositioning(true),
        { passive: true }
    );
    chartElement.addEventListener(
        "dblclick",
        () => scheduleZonePositioning(true),
        { passive: true }
    );

    const resizeObserver = new ResizeObserver(() => {
        chart.applyOptions({
            width: chartElement.clientWidth,
            height: chartElement.clientHeight
        });
        scheduleZonePositioning(true);
    });

    resizeObserver.observe(chartElement);

    const workspace = document.querySelector(".workspace");
    const workspaceResizer = document.getElementById("workspace-resizer");
    const strategyPanel = document.querySelector(".strategy-panel");
    const defaultStrategyWidth = 285;

    function setStrategyWidth(width, persist = false) {
        if (!workspace || !strategyPanel) {
            return;
        }

        const workspaceWidth = workspace.getBoundingClientRect().width;
        const maximumWidth = Math.min(430, workspaceWidth * 0.46);
        const safeWidth = Math.max(
            265,
            Math.min(Number(width) || defaultStrategyWidth, maximumWidth)
        );

        workspace.style.setProperty(
            "--strategy-width",
            `${Math.round(safeWidth)}px`
        );

        if (workspaceResizer) {
            workspaceResizer.setAttribute(
                "aria-valuenow",
                String(Math.round(safeWidth))
            );
        }

        if (persist) {
            localStorage.setItem(
                "btc-dashboard-strategy-width",
                String(Math.round(safeWidth))
            );
        }
    }

    if (workspace && workspaceResizer && strategyPanel) {
        const savedWidth = Number(
            localStorage.getItem("btc-dashboard-strategy-width")
        );
        setStrategyWidth(savedWidth || defaultStrategyWidth);

        workspaceResizer.addEventListener("pointerdown", (event) => {
            event.preventDefault();
            workspaceResizer.setPointerCapture(event.pointerId);
            document.body.classList.add("is-resizing-workspace");
        });

        workspaceResizer.addEventListener("pointermove", (event) => {
            if (!workspaceResizer.hasPointerCapture(event.pointerId)) {
                return;
            }

            const workspaceRect = workspace.getBoundingClientRect();
            setStrategyWidth(workspaceRect.right - event.clientX);
        });

        function finishResize(event) {
            if (workspaceResizer.hasPointerCapture(event.pointerId)) {
                workspaceResizer.releasePointerCapture(event.pointerId);
            }

            document.body.classList.remove("is-resizing-workspace");
            setStrategyWidth(
                strategyPanel.getBoundingClientRect().width,
                true
            );
        }

        workspaceResizer.addEventListener("pointerup", finishResize);
        workspaceResizer.addEventListener("pointercancel", finishResize);

        workspaceResizer.addEventListener("dblclick", () => {
            setStrategyWidth(defaultStrategyWidth, true);
        });

        workspaceResizer.addEventListener("keydown", (event) => {
            if (!["ArrowLeft", "ArrowRight"].includes(event.key)) {
                return;
            }

            event.preventDefault();
            const currentWidth = strategyPanel.getBoundingClientRect().width;
            const adjustment = event.key === "ArrowLeft" ? 15 : -15;
            setStrategyWidth(currentWidth + adjustment, true);
        });

        window.addEventListener("resize", () => {
            setStrategyWidth(
                strategyPanel.getBoundingClientRect().width
            );
        });
    }

    await loadTimeframe(
        chartElement.dataset.defaultTimeframe || "240",
        chartElement.dataset.defaultTimeframeLabel || "4H"
    );

    window.setInterval(() => {
        if (
            document.hidden
            || timeframeButtons.some((button) => button.disabled)
        ) {
            return;
        }

        loadTimeframe(
            activeTimeframe,
            activeTimeframeLabel,
            { silent: true, fitContent: false }
        );
    }, 30_000);

    const aiButton = document.getElementById("generate-ai-report");
    const aiReportText = document.getElementById("ai-report-text");

    if (aiButton && aiReportText) {
        aiButton.addEventListener("click", async () => {
            aiButton.disabled = true;
            aiButton.textContent = "AI анализирует…";
            aiReportText.className = "ai-report-placeholder";
            aiReportText.textContent = "Формируем объяснение текущего решения…";

            try {
                const aiUrl = new URL(
                    aiButton.dataset.apiUrl,
                    window.location.origin
                );
                aiUrl.searchParams.set(
                    "strategy",
                    aiButton.dataset.strategy || "swing"
                );
                aiUrl.searchParams.set("symbol", activeSymbol);
                const response = await fetch(aiUrl, {
                    method: "POST",
                    headers: { Accept: "application/json" }
                });
                const payload = await response.json();

                if (!response.ok) {
                    throw new Error(payload.error || `HTTP ${response.status}`);
                }

                aiReportText.className = "ai-report-text";
                aiReportText.textContent = payload.report;
                aiButton.textContent = "Обновить AI-комментарий";
            } catch (error) {
                console.error(error);
                aiReportText.className = "ai-report-error";
                aiReportText.textContent = (
                    "Не удалось получить AI-комментарий. "
                    + "Проверьте OPENAI_API_KEY и повторите попытку."
                );
                aiButton.textContent = "Повторить";
            } finally {
                aiButton.disabled = false;
            }
        });
    }

    const whalePanel = document.getElementById("whale-alert-panel");
    const whaleSummary = document.getElementById("whale-summary");
    const whaleEvents = document.getElementById("whale-events");

    async function loadWhaleContext() {
        if (!whalePanel || !whaleSummary || !whaleEvents) {
            return;
        }

        try {
            const response = await fetch(whalePanel.dataset.apiUrl, {
                headers: { Accept: "application/json" }
            });
            const payload = await response.json();

            if (!response.ok || !payload.available) {
                throw new Error(payload.error || `HTTP ${response.status}`);
            }

            const sentimentClass = payload.score > 0
                ? "is-positive"
                : payload.score < 0
                    ? "is-negative"
                    : "is-neutral";

            whaleSummary.className = `whale-summary ${sentimentClass}`;
            whaleSummary.innerHTML = `
                <div><span>Активность</span><strong>${payload.activity}</strong></div>
                <div><span>Общий фон</span><strong>${payload.sentiment}</strong></div>
                <div><span>BTC на биржи</span><strong>$${payload.totals.btc_to_exchanges} млн</strong></div>
                <div><span>BTC с бирж</span><strong>$${payload.totals.btc_from_exchanges} млн</strong></div>
                <div><span>Стейблкоины на биржи</span><strong>$${payload.totals.stable_to_exchanges} млн</strong></div>
            `;
            whaleEvents.replaceChildren();

            payload.events.slice(0, 5).forEach((event) => {
                const link = document.createElement("a");
                const impact = event.impact > 0
                    ? "🟢"
                    : event.impact < 0
                        ? "🔴"
                        : "⚪";

                link.className = "whale-event";
                link.href = event.url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.innerHTML = `
                    <span>${impact}</span>
                    <span>
                        <strong>${event.category}</strong>
                        <small>${event.symbol} · $${event.value_millions} млн</small>
                    </span>
                `;
                whaleEvents.appendChild(link);
            });

            if (!payload.events.length) {
                whaleEvents.textContent = (
                    "Крупных подходящих событий в последних публикациях нет."
                );
            }
        } catch (error) {
            console.error(error);
            whaleSummary.className = "whale-summary is-unavailable";
            whaleSummary.textContent = (
                "Whale Alert временно недоступен. "
                + "Основная стратегия продолжает работать без этого фильтра."
            );
        }
    }

    loadWhaleContext();

    const newsPanel = document.getElementById("crypto-news-panel");
    const newsSummary = document.getElementById("news-summary");
    const newsList = document.getElementById("news-list");

    async function loadCryptoNews() {
        if (!newsPanel || !newsSummary || !newsList) {
            return;
        }

        try {
            const response = await fetch(newsPanel.dataset.apiUrl, {
                headers: { Accept: "application/json" }
            });
            const payload = await response.json();

            if (!response.ok || !payload.available) {
                throw new Error(payload.error || `HTTP ${response.status}`);
            }

            const sentimentClass = payload.score > 0
                ? "is-positive"
                : payload.score < 0
                    ? "is-negative"
                    : "is-neutral";

            newsSummary.className = `news-summary ${sentimentClass}`;
            newsSummary.innerHTML = `
                <div>
                    <span>Новостной фон</span>
                    <strong>${payload.sentiment}</strong>
                </div>
                <div>
                    <span>Важных публикаций</span>
                    <strong>${payload.high_importance_count}</strong>
                </div>
                <div>
                    <span>Проанализировано</span>
                    <strong>${payload.articles.length}</strong>
                </div>
            `;
            newsList.replaceChildren();

            payload.articles.slice(0, 6).forEach((article) => {
                const link = document.createElement("a");
                const indicator = article.score > 0
                    ? "🟢"
                    : article.score < 0
                        ? "🔴"
                        : "⚪";

                link.className = "news-item";
                link.href = article.url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";

                const indicatorElement = document.createElement("span");
                indicatorElement.textContent = indicator;

                const content = document.createElement("span");
                const title = document.createElement("strong");
                const metadata = document.createElement("small");

                title.textContent = article.title;
                metadata.textContent = (
                    `${article.importance} важность · ${article.sentiment}`
                );
                content.append(title, metadata);
                link.append(indicatorElement, content);
                newsList.appendChild(link);
            });

            if (!payload.articles.length) {
                newsList.textContent = "Подходящих свежих новостей сейчас нет.";
            }
        } catch (error) {
            console.error(error);
            newsSummary.className = "news-summary is-unavailable";
            newsSummary.textContent = (
                "CryptoNews временно недоступен. "
                + "Основная стратегия продолжает работать без новостного фильтра."
            );
        }
    }

    loadCryptoNews();

    const tradeStatus = document.getElementById("trade-status");
    const sellPriceField = document.getElementById("sell-price-field");
    const sellPriceInput = document.getElementById("sell-price");

    if (tradeStatus && sellPriceField && sellPriceInput) {
        function updateSellPriceVisibility() {
            const isClosed = tradeStatus.value === "CLOSED";

            sellPriceField.hidden = !isClosed;
            sellPriceInput.required = isClosed;

            if (!isClosed) {
                sellPriceInput.value = "";
            }
        }

        tradeStatus.addEventListener("change", updateSellPriceVisibility);
        updateSellPriceVisibility();
    }

    function initializeResizableOrderColumns() {
        const table = document.getElementById("open-orders-table");

        if (!table) {
            return;
        }

        const headers = Array.from(table.querySelectorAll("thead th"));
        const storageKey = (
            `open-orders-column-widths-${table.dataset.symbol || "default"}`
        );

        function updateTableWidth() {
            const totalWidth = headers.reduce(
                (total, header) => total + header.getBoundingClientRect().width,
                0
            );
            table.style.width = `${Math.ceil(totalWidth)}px`;
        }

        try {
            const savedWidths = JSON.parse(
                localStorage.getItem(storageKey) || "null"
            );

            if (
                Array.isArray(savedWidths)
                && savedWidths.length === headers.length
            ) {
                headers.forEach((header, index) => {
                    const width = Number(savedWidths[index]);
                    if (Number.isFinite(width) && width >= 70) {
                        header.style.width = `${width}px`;
                    }
                });
                requestAnimationFrame(updateTableWidth);
            }
        } catch (error) {
            console.warn("Не удалось восстановить ширину колонок", error);
        }

        headers.forEach((header) => {
            const resizer = document.createElement("span");
            resizer.className = "column-resizer";
            resizer.title = "Потяните для изменения ширины";
            header.appendChild(resizer);

            resizer.addEventListener("dblclick", (event) => {
                event.preventDefault();
                localStorage.removeItem(storageKey);
                window.location.reload();
            });

            resizer.addEventListener("pointerdown", (event) => {
                event.preventDefault();
                resizer.setPointerCapture(event.pointerId);

                const startX = event.clientX;
                const startWidth = header.getBoundingClientRect().width;
                const startTableWidth = table.getBoundingClientRect().width;

                resizer.classList.add("is-active");
                document.body.classList.add("is-resizing-column");

                function onPointerMove(moveEvent) {
                    const delta = moveEvent.clientX - startX;
                    const nextWidth = Math.max(70, startWidth + delta);
                    const appliedDelta = nextWidth - startWidth;

                    header.style.width = `${Math.round(nextWidth)}px`;
                    table.style.width = (
                        `${Math.round(startTableWidth + appliedDelta)}px`
                    );
                }

                function onPointerUp() {
                    resizer.classList.remove("is-active");
                    document.body.classList.remove("is-resizing-column");
                    resizer.removeEventListener("pointermove", onPointerMove);
                    resizer.removeEventListener("pointerup", onPointerUp);
                    resizer.removeEventListener("pointercancel", onPointerUp);

                    const widths = headers.map(
                        (item) => Math.round(item.getBoundingClientRect().width)
                    );
                    localStorage.setItem(storageKey, JSON.stringify(widths));
                }

                resizer.addEventListener("pointermove", onPointerMove);
                resizer.addEventListener("pointerup", onPointerUp);
                resizer.addEventListener("pointercancel", onPointerUp);
            });
        });
    }

    initializeResizableOrderColumns();
})();

(function initializeBalanceVisibility() {
    const toggle = document.getElementById("hide-small-balances");
    const balances = Array.from(
        document.querySelectorAll(".exchange-balance[data-usd-value]")
    );

    if (!toggle || balances.length === 0) {
        return;
    }

    const storageKey = "okx-hide-small-balances";

    function applyBalanceFilter() {
        balances.forEach((balance) => {
            const usdValue = Number(balance.dataset.usdValue || 0);
            balance.hidden = toggle.checked && usdValue < 1;
        });
        localStorage.setItem(storageKey, toggle.checked ? "1" : "0");
    }

    toggle.checked = localStorage.getItem(storageKey) === "1";
    toggle.addEventListener("change", applyBalanceFilter);
    applyBalanceFilter();
})();

(function initializeLevelCopyButtons() {
    const buttons = Array.from(
        document.querySelectorAll(".copy-level-button[data-copy-target]")
    );

    buttons.forEach((button) => {
        button.addEventListener("click", async () => {
            const target = document.getElementById(button.dataset.copyTarget);
            if (!target) {
                return;
            }

            const value = target.textContent.replace(/\s+/g, "").trim();

            try {
                await navigator.clipboard.writeText(value);
                const originalText = button.textContent;
                button.textContent = "Скопировано";
                button.classList.add("is-copied");
                window.setTimeout(() => {
                    button.textContent = originalText;
                    button.classList.remove("is-copied");
                }, 1400);
            } catch (error) {
                console.warn("Не удалось скопировать уровень", error);
            }
        });
    });
})();
