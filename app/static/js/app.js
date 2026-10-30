(() => {
  // Mantém ações destrutivas explícitas: o formulário só continua após confirmação.
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  // Evita submissões repetidas e dá retorno visual durante o processamento.
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', event => {
      if (event.defaultPrevented) return;
      const button = form.querySelector('.action-loading');
      if (button) {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Processando...';
      }
    });
  });
  // Em telas estreitas, fecha o menu lateral depois da navegação.
  document.querySelectorAll('.sidebar .nav-item').forEach(link => {
    link.addEventListener('click', () => document.getElementById('sidebar')?.classList.remove('open'));
  });
})();
