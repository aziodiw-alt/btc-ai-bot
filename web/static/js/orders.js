document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("order-image");
    const pasteZone = document.getElementById("clipboard-drop-zone");
    const preview = document.getElementById("clipboard-preview");
    const status = document.getElementById("clipboard-status");

    if (!fileInput || !pasteZone || !preview || !status) {
        return;
    }

    function showImage(file) {
        if (!file || !file.type.startsWith("image/")) {
            status.textContent = "В буфере обмена нет изображения.";
            status.classList.add("status-skip");
            return;
        }

        const dataTransfer = new DataTransfer();
        const extension = file.type === "image/jpeg" ? "jpg" : "png";
        const clipboardFile = new File(
            [file],
            `bybit-open-orders-${Date.now()}.${extension}`,
            { type: file.type }
        );
        dataTransfer.items.add(clipboardFile);
        fileInput.files = dataTransfer.files;

        preview.src = URL.createObjectURL(clipboardFile);
        preview.hidden = false;
        pasteZone.classList.add("has-image");
        status.textContent =
            "Скриншот вставлен. Нажмите «Распознать и проверить».";
        status.classList.remove("status-skip");
        status.classList.add("status-buy");
    }

    document.addEventListener("paste", (event) => {
        const items = Array.from(event.clipboardData?.items || []);
        const imageItem = items.find((item) => item.type.startsWith("image/"));

        if (!imageItem) {
            return;
        }

        event.preventDefault();
        showImage(imageItem.getAsFile());
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length) {
            showImage(fileInput.files[0]);
        }
    });

    pasteZone.addEventListener("click", () => {
        pasteZone.focus();
    });
});
