const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
const toggle = document.querySelector('#motion-toggle');
let paused = reducedMotion.matches;
let active = null;
let frame = 0;

function reset() {
  cancelAnimationFrame(frame);
  if (active) {
    active.style.removeProperty('--rx');
    active.style.removeProperty('--ry');
    active.style.removeProperty('--light-x');
    active.style.removeProperty('--light-y');
    active.classList.remove('is-tilting');
  }
  active = null;
}
function sync() {
  reset();
  document.body.classList.toggle('motion-paused', paused || reducedMotion.matches);
  toggle.setAttribute('aria-pressed', String(paused));
  toggle.disabled = reducedMotion.matches;
  toggle.innerHTML = reducedMotion.matches ? 'Reduced motion' : paused ? 'Resume motion <span aria-hidden="true">▷</span>' : 'Pause motion <span aria-hidden="true">Ⅱ</span>';
}
toggle.addEventListener('click', () => { paused = !paused; sync(); });
reducedMotion.addEventListener('change', () => { paused = reducedMotion.matches; sync(); });
finePointer.addEventListener('change', reset);
// Delegation also covers catalog cards created after API calls or filtering.
document.addEventListener('pointermove', event => {
  if (paused || reducedMotion.matches || !finePointer.matches || event.pointerType === 'touch') return;
  const target = event.target.closest('[data-tilt], .product-art, .detail-art');
  if (target !== active) { reset(); active = target; }
  if (!target) return;
  const bounds = target.getBoundingClientRect();
  const x = (event.clientX - bounds.left) / bounds.width;
  const y = (event.clientY - bounds.top) / bounds.height;
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(() => {
    target.style.setProperty('--rx', `${(0.5 - y) * 9}deg`);
    target.style.setProperty('--ry', `${(x - 0.5) * 12}deg`);
    target.style.setProperty('--light-x', `${x * 100}%`);
    target.style.setProperty('--light-y', `${y * 100}%`);
    target.classList.add('is-tilting');
  });
});
document.documentElement.addEventListener('pointerleave', reset);
window.addEventListener('blur', reset);
document.addEventListener('visibilitychange', () => { if (document.hidden) reset(); });
sync();
