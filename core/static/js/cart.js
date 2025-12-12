document.addEventListener("DOMContentLoaded", () => {

    function getCSRF() {
        const cookie = document.cookie.split("; ").find(c => c.startsWith("csrftoken="));
        return cookie ? cookie.split("=")[1] : "";
    }

    document.querySelectorAll(".cart-item").forEach(row => {

        const form = row.querySelector(".qty-form");
        const qtyInput = row.querySelector(".qty-input");
        const btnInc = row.querySelector(".increase");
        const btnDec = row.querySelector(".decrease");

        btnInc.addEventListener("click", () => {
            qtyInput.value = parseInt(qtyInput.value) + 1;
            updateCart("increase");
        });

        btnDec.addEventListener("click", () => {
            if (parseInt(qtyInput.value) > 1) {
                qtyInput.value = parseInt(qtyInput.value) - 1;
                updateCart("decrease");
            }
        });

        function updateCart(action) {
            const url = form.action;

            const formData = new FormData();
            formData.append("action", action);
            formData.append("quantity", qtyInput.value);

            fetch(url, {
                method: "POST",
                headers: { "X-CSRFToken": getCSRF() },
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (!data.success) return;

                // ITEM FINAL
                row.querySelector(".final-price").innerText =
                    "₹" + parseFloat(data.item_final).toFixed(2);

                // SUMMARY
                document.getElementById("subtotal").innerText =
                    "₹" + parseFloat(data.subtotal).toFixed(2);

                document.getElementById("tax").innerText =
                    "₹" + parseFloat(data.tax).toFixed(2);

                document.getElementById("total").innerText =
                    "₹" + parseFloat(data.total).toFixed(2);
            });
        }
    });
});
