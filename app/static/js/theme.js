// Dark / light mode toggle. The theme is applied pre-paint in base.html;
// this only wires the button and persists the choice.
(function () {
  const button = document.getElementById('theme-toggle');
  if (!button) return;

  const icon = button.querySelector('i');

  function render(theme) {
    icon.className = theme === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
  }

  render(document.documentElement.getAttribute('data-bs-theme'));

  button.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-bs-theme') === 'dark'
      ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', next);
    localStorage.setItem('theme', next);
    render(next);
  });
})();
