document.addEventListener("DOMContentLoaded", () => {

  // -----------------------------
  // Grab DOM elements
  // -----------------------------
  const basePrice = parseFloat(document.getElementById("basePrice").value);
  const discountPrice = parseFloat(document.getElementById("discountPrice").value);
  const isOffer = document.getElementById("isOfferActive").value === "True";

  const quantityInput = document.getElementById("quantityInput");
  const weightDropdown = document.getElementById("weightDropdown");
  const selectedWeightHidden = document.getElementById("selectedWeight");
  const selectedWeightText = document.getElementById("selectedWeightText");

  const livePriceEl = document.getElementById("livePrice");
  const liveUnitEl = document.getElementById("livePriceUnit");

  const trueUnitPriceField = document.getElementById("trueUnitPrice");


  // -----------------------------
  // Dropdown open / close
  // -----------------------------
  document.getElementById("weightSelector").addEventListener("click", () => {
      weightDropdown.classList.toggle("d-none");
  });


  // -----------------------------
  // Helper: get multiplier
  // -----------------------------
  function getWeightMultiplier() {
      const selected = selectedWeightHidden.value;
      const li = [...weightDropdown.children].find(li => li.dataset.value === selected);
      if (!li) return 1;

      return parseFloat(li.dataset.valNum || "1");
  }


  // -----------------------------
  // Calculate unit price
  // -----------------------------
  function calculateUnitPrice() {
      const multiplier = getWeightMultiplier();

      const base = isOffer ? discountPrice : basePrice;

      const unitPrice = base * multiplier;
      return Number(unitPrice.toFixed(2));
  }


  // -----------------------------
  // Update UI
  // -----------------------------
  function updateUI() {
    const pricePerItem = calculateUnitPrice();   // base × weight
    const qty = parseInt(quantityInput.value) || 1;

    const finalPrice = pricePerItem * qty;

    livePriceEl.innerText = "₹" + finalPrice.toFixed(2);

    const li = [...weightDropdown.children].find(li => li.dataset.value === selectedWeightHidden.value);
    if (li) {
        liveUnitEl.innerText = `${qty} × ${li.dataset.value} = ₹${finalPrice.toFixed(2)}`;
    }

    trueUnitPriceField.value = pricePerItem.toFixed(2);   // only price of 1 item
}


  // -----------------------------
  // Weight selection
  // -----------------------------
  document.querySelectorAll("#weightDropdown li").forEach(li => {
      li.addEventListener("click", () => {
          const weight = li.dataset.value;

          selectedWeightHidden.value = weight;
          selectedWeightText.innerText = weight;

          updateUI();
          weightDropdown.classList.add("d-none");
      });
  });


  // -----------------------------
  // Quantity +/–
  // -----------------------------
  document.querySelector(".qty-btn.plus").addEventListener("click", () => {
      quantityInput.value = parseInt(quantityInput.value) + 1;
      updateUI();
  });

  document.querySelector(".qty-btn.minus").addEventListener("click", () => {
      const current = parseInt(quantityInput.value);
      if (current > 1) quantityInput.value = current - 1;
      updateUI();
  });


  // -----------------------------
  // Set final price before submit
  // -----------------------------
  document.getElementById("addToCartForm").addEventListener("submit", () => {
      trueUnitPriceField.value = calculateUnitPrice().toFixed(2);
  });


  // -----------------------------
  // INIT
  // -----------------------------
  updateUI();

});
