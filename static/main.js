const targetButtons = document.querySelectorAll("[data-target]");
const topMark = document.getElementById("topMark");
const heroLogo = document.getElementById("heroLogo");

targetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const target = document.querySelector(button.dataset.target);
    if (target) {
      smoothScrollTo(target, 1600);
    }
  });
});

function easeInOutCubic(t) {
  return t < 0.5
    ? 4 * t * t * t
    : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function smoothScrollTo(element, duration = 1600) {
  const start = window.pageYOffset;
  const targetY = element.getBoundingClientRect().top + window.pageYOffset;
  const distance = targetY - start;
  const startTime = performance.now();

  function step(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = easeInOutCubic(progress);

    window.scrollTo(0, start + distance * eased);

    if (progress < 1) {
      requestAnimationFrame(step);
    }
  }

  requestAnimationFrame(step);
}

let smoothY = window.scrollY;

function animate() {
  const realY = window.scrollY;
  smoothY += (realY - smoothY) * 0.065;

  const vh = window.innerHeight || 1;
  const progress = Math.min(smoothY / (vh * 0.7), 1);

  if (heroLogo) {
    const scale = 1 - progress * 0.14;
    const opacity = 1 - progress * 1.08;
    const blur = progress * 1.2;

    heroLogo.style.transform = `scale(${scale})`;
    heroLogo.style.opacity = `${Math.max(opacity, 0)}`;
    heroLogo.style.filter = `
      drop-shadow(0 0 16px rgba(255,255,255,0.08))
      drop-shadow(0 0 44px rgba(255,255,255,0.05))
      blur(${blur}px)
    `;
  }

  if (topMark) {
    const markProgress = Math.max(0, Math.min((smoothY - vh * 0.18) / (vh * 0.28), 1));
    topMark.style.opacity = `${markProgress}`;
    topMark.style.transform = `translateX(-50%) translateY(${(1 - markProgress) * -18}px)`;
  }

  requestAnimationFrame(animate);
}

requestAnimationFrame(animate);
