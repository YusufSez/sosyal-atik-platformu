(function () {
  function checkRules(password) {
    return {
      length: password.length >= 8,
      upper: /[A-Z]/.test(password),
      lower: /[a-z]/.test(password),
      digit: /[0-9]/.test(password),
    };
  }

  function allRulesMet(rules) {
    return rules.length && rules.upper && rules.lower && rules.digit;
  }

  window.PasswordValidation = {
    init: function (options) {
      options = options || {};
      var passwordEl = document.getElementById(options.passwordId || "password");
      var confirmEl = document.getElementById(options.confirmId || "password_tekrar");
      var formEl = document.getElementById(options.formId);
      var rulesEl = document.getElementById(options.rulesId || "passwordRules");
      var matchEl = document.getElementById(options.matchId || "passwordMatch");
      var submitEl = options.submitId ? document.getElementById(options.submitId) : null;

      if (!passwordEl || !rulesEl) return;

      function notifyChange(strengthOk, matchOk) {
        if (typeof options.onChange === "function") {
          options.onChange(strengthOk && matchOk);
        }
      }

      function setSubmitDisabled(disabled) {
        if (submitEl) {
          submitEl.disabled = disabled;
        }
      }

      function setRuleState(rule, ok) {
        var item = rulesEl.querySelector('[data-rule="' + rule + '"]');
        if (!item) return;
        item.classList.toggle("is-valid", ok);
        item.classList.toggle("is-invalid", !ok);
        var icon = item.querySelector(".rule-icon");
        if (icon) {
          icon.textContent = ok ? "✓" : "○";
        }
      }

      function updateMatch() {
        if (!matchEl || !confirmEl) return true;
        var password = passwordEl.value;
        var confirm = confirmEl.value;
        if (!confirm) {
          matchEl.textContent = "";
          matchEl.className = "password-match small mt-2 text-muted";
          return false;
        }
        if (password === confirm) {
          matchEl.textContent = "Parolalar eşleşiyor.";
          matchEl.className = "password-match small mt-2 text-success";
          return true;
        }
        matchEl.textContent = "Parolalar eşleşmiyor.";
        matchEl.className = "password-match small mt-2 text-danger";
        return false;
      }

      function update() {
        var rules = checkRules(passwordEl.value);
        setRuleState("length", rules.length);
        setRuleState("upper", rules.upper);
        setRuleState("lower", rules.lower);
        setRuleState("digit", rules.digit);

        var strengthOk = allRulesMet(rules);
        var matchOk = !confirmEl || !confirmEl.value ? false : updateMatch();

        if (!options.onChange) {
          setSubmitDisabled(!(strengthOk && matchOk));
        }
        notifyChange(strengthOk, matchOk);
        return strengthOk && matchOk;
      }

      passwordEl.addEventListener("input", update);
      if (confirmEl) {
        confirmEl.addEventListener("input", update);
      }

      if (formEl) {
        formEl.addEventListener("submit", function (e) {
          if (!update()) {
            e.preventDefault();
            if (!allRulesMet(checkRules(passwordEl.value))) {
              passwordEl.focus();
            } else if (confirmEl) {
              confirmEl.focus();
            }
          }
        });
      }

      update();
    },
  };
})();
