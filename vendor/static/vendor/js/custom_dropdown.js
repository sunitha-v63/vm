document.addEventListener("DOMContentLoaded", function () {
    const selectBox = document.querySelector(".custom-select-box");

    if (!selectBox) return;  // stop script if dropdown doesn't exist

    const selectedOption = selectBox.querySelector(".selected-option");
    const options = selectBox.querySelectorAll(".custom-options li");
    const hiddenInput = selectBox.querySelector("input[type='hidden']");

    // Toggle dropdown
    selectedOption.addEventListener("click", function () {
        selectBox.classList.toggle("active");
    });

    // Select option
    options.forEach(option => {
        option.addEventListener("click", function () {

            selectedOption.textContent = this.textContent;
            hiddenInput.value = this.dataset.value;

            options.forEach(opt => opt.classList.remove("selected"));
            this.classList.add("selected");

            selectBox.classList.remove("active");
        });
    });

    // Close dropdown when clicking outside
    document.addEventListener("click", function (e) {
        if (!selectBox.contains(e.target)) {
            selectBox.classList.remove("active");
        }
    });
});
