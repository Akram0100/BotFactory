// BotFactory Main JavaScript

// Global utilities and initialization
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// Initialize application
function initializeApp() {
    initializeTooltips();
    initializePopovers();
    initializeFormValidation();
    initializeAutoResize();
    initializeConfirmations();
    initializeLoadingStates();
    initializeCharacterCounters();
    initializeSearchFilters();
    
    console.log('BotFactory initialized successfully');
}

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialize Bootstrap popovers
function initializePopovers() {
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
}

// Form validation utilities
function initializeFormValidation() {
    // Bootstrap form validation
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // Custom validation rules
    addCustomValidationRules();
}

// Custom validation rules
function addCustomValidationRules() {
    // Username validation
    const usernameInputs = document.querySelectorAll('input[name="username"]');
    usernameInputs.forEach(input => {
        input.addEventListener('input', function() {
            const username = this.value;
            const pattern = /^[a-zA-Z0-9_]{3,30}$/;
            
            if (username && !pattern.test(username)) {
                this.setCustomValidity('Username must be 3-30 characters and contain only letters, numbers, and underscores');
            } else {
                this.setCustomValidity('');
            }
        });
    });

    // Password confirmation
    const confirmPasswordInputs = document.querySelectorAll('input[name="confirm_password"]');
    confirmPasswordInputs.forEach(input => {
        input.addEventListener('input', function() {
            const password = document.querySelector('input[name="password"]')?.value;
            const confirmPassword = this.value;
            
            if (confirmPassword && password !== confirmPassword) {
                this.setCustomValidity('Passwords do not match');
            } else {
                this.setCustomValidity('');
            }
        });
    });

    // Telegram token validation
    const tokenInputs = document.querySelectorAll('input[name="telegram_token"]');
    tokenInputs.forEach(input => {
        input.addEventListener('input', function() {
            const token = this.value;
            const pattern = /^\d{8,10}:[A-Za-z0-9_-]{35}$/;
            
            if (token && !pattern.test(token)) {
                this.setCustomValidity('Invalid Telegram bot token format');
            } else {
                this.setCustomValidity('');
            }
        });
    });
}

// Auto-resize textareas
function initializeAutoResize() {
    const textareas = document.querySelectorAll('textarea[data-auto-resize]');
    textareas.forEach(textarea => {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
        
        // Initial resize
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
    });
}

// Confirmation dialogs
function initializeConfirmations() {
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.dataset.confirm || 'Are you sure?';
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });
}

// Loading states for forms
function initializeLoadingStates() {
    const forms = document.querySelectorAll('form[data-loading]');
    forms.forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                const originalHtml = submitBtn.innerHTML;
                const loadingText = submitBtn.dataset.loading || 'Loading...';
                
                submitBtn.disabled = true;
                submitBtn.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i>${loadingText}`;
                
                // Reset after 10 seconds (fallback)
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalHtml;
                }, 10000);
            }
        });
    });
}

// Character counters for textareas and inputs
function initializeCharacterCounters() {
    const elementsWithCounter = document.querySelectorAll('[data-max-length]');
    elementsWithCounter.forEach(element => {
        addCharacterCounter(element);
    });
}

function addCharacterCounter(element) {
    const maxLength = parseInt(element.dataset.maxLength);
    if (!maxLength) return;

    const counter = document.createElement('div');
    counter.className = 'form-text text-end character-counter';
    element.parentNode.appendChild(counter);

    function updateCounter() {
        const length = element.value.length;
        counter.textContent = `${length.toLocaleString()}/${maxLength.toLocaleString()} characters`;
        
        if (length > maxLength * 0.9) {
            counter.className = 'form-text text-end character-counter text-warning';
        } else if (length > maxLength) {
            counter.className = 'form-text text-end character-counter text-danger';
        } else {
            counter.className = 'form-text text-end character-counter text-muted';
        }
    }

    element.addEventListener('input', updateCounter);
    updateCounter();
}

// Search and filter functionality
function initializeSearchFilters() {
    const searchInputs = document.querySelectorAll('[data-search-target]');
    searchInputs.forEach(input => {
        const targetSelector = input.dataset.searchTarget;
        const targets = document.querySelectorAll(targetSelector);
        
        input.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            
            targets.forEach(target => {
                const text = target.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    target.style.display = '';
                } else {
                    target.style.display = 'none';
                }
            });
        });
    });
}

// API utilities
const API = {
    // Generic API call function
    async call(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        };

        const finalOptions = { ...defaultOptions, ...options };
        
        try {
            const response = await fetch(url, finalOptions);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return await response.text();
            }
        } catch (error) {
            console.error('API call failed:', error);
            throw error;
        }
    },

    // Test bot response
    async testBot(botId, message) {
        return this.call(`/api/bot/${botId}/test`, {
            method: 'POST',
            body: JSON.stringify({ message })
        });
    },

    // Get bot statistics
    async getBotStats(botId) {
        return this.call(`/api/bot/${botId}/stats`);
    },

    // Update bot status
    async updateBotStatus(botId, status) {
        return this.call(`/api/bot/${botId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
    }
};

// Notification system
const Notifications = {
    show(message, type = 'info', duration = 5000) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        
        alertDiv.innerHTML = `
            ${this.getIcon(type)}
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(alertDiv);

        // Auto-remove after duration
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, duration);
    },

    getIcon(type) {
        const icons = {
            success: '<i class="fas fa-check-circle me-2"></i>',
            danger: '<i class="fas fa-exclamation-circle me-2"></i>',
            warning: '<i class="fas fa-exclamation-triangle me-2"></i>',
            info: '<i class="fas fa-info-circle me-2"></i>'
        };
        return icons[type] || icons.info;
    },

    success(message) {
        this.show(message, 'success');
    },

    error(message) {
        this.show(message, 'danger');
    },

    warning(message) {
        this.show(message, 'warning');
    },

    info(message) {
        this.show(message, 'info');
    }
};

// Local storage utilities
const Storage = {
    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.warn('Failed to save to localStorage:', error);
        }
    },

    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (error) {
            console.warn('Failed to read from localStorage:', error);
            return defaultValue;
        }
    },

    remove(key) {
        try {
            localStorage.removeItem(key);
        } catch (error) {
            console.warn('Failed to remove from localStorage:', error);
        }
    }
};

// Theme utilities
const Theme = {
    init() {
        // Auto-detect system theme preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
            this.setTheme('light');
        } else {
            this.setTheme('dark');
        }

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
            this.setTheme(e.matches ? 'dark' : 'light');
        });
    },

    setTheme(theme) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        Storage.set('theme', theme);
    },

    getTheme() {
        return Storage.get('theme', 'dark');
    },

    toggle() {
        const currentTheme = this.getTheme();
        this.setTheme(currentTheme === 'dark' ? 'light' : 'dark');
    }
};

// Copy to clipboard utility
function copyToClipboard(text, successMessage = 'Copied to clipboard!') {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => {
            Notifications.success(successMessage);
        }).catch(err => {
            console.error('Failed to copy: ', err);
            Notifications.error('Failed to copy to clipboard');
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        
        try {
            document.execCommand('copy');
            Notifications.success(successMessage);
        } catch (err) {
            console.error('Fallback copy failed: ', err);
            Notifications.error('Failed to copy to clipboard');
        }
        
        document.body.removeChild(textArea);
    }
}

// Format numbers for display
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    } else {
        return num.toString();
    }
}

// Format dates for display
function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 1) {
        return 'Yesterday';
    } else if (diffDays < 7) {
        return `${diffDays} days ago`;
    } else if (diffDays < 30) {
        const weeks = Math.floor(diffDays / 7);
        return `${weeks} week${weeks > 1 ? 's' : ''} ago`;
    } else {
        return date.toLocaleDateString();
    }
}

// Debounce function for search inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Smooth scroll to element
function scrollToElement(selector, offset = 0) {
    const element = document.querySelector(selector);
    if (element) {
        const elementPosition = element.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - offset;

        window.scrollTo({
            top: offsetPosition,
            behavior: 'smooth'
        });
    }
}

// Auto-save form data
function initializeAutoSave() {
    const autoSaveForms = document.querySelectorAll('[data-auto-save]');
    
    autoSaveForms.forEach(form => {
        const formId = form.id || form.dataset.autoSave;
        if (!formId) return;

        // Load saved data
        const savedData = Storage.get(`autosave_${formId}`);
        if (savedData) {
            Object.keys(savedData).forEach(name => {
                const field = form.querySelector(`[name="${name}"]`);
                if (field && field.type !== 'password') {
                    field.value = savedData[name];
                }
            });
        }

        // Save data on input
        const debouncedSave = debounce(() => {
            const formData = new FormData(form);
            const data = {};
            for (let [key, value] of formData.entries()) {
                if (form.querySelector(`[name="${key}"]`).type !== 'password') {
                    data[key] = value;
                }
            }
            Storage.set(`autosave_${formId}`, data);
        }, 1000);

        form.addEventListener('input', debouncedSave);

        // Clear saved data on successful submit
        form.addEventListener('submit', () => {
            Storage.remove(`autosave_${formId}`);
        });
    });
}

// Initialize auto-save when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeAutoSave);

// Global error handler
window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    
    // Don't show notifications for script loading errors
    if (e.error && e.error.stack && !e.error.stack.includes('script')) {
        Notifications.error('An unexpected error occurred. Please try again.');
    }
});

// Global promise rejection handler
window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
    Notifications.error('A network error occurred. Please check your connection.');
});

// Expose utilities globally
window.BotFactory = {
    API,
    Notifications,
    Storage,
    Theme,
    copyToClipboard,
    formatNumber,
    formatDate,
    debounce,
    scrollToElement
};

// Initialize theme on load
document.addEventListener('DOMContentLoaded', () => {
    Theme.init();
});

// Service worker registration for PWA features (if needed)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        // Only register if service worker file exists
        fetch('/sw.js').then(response => {
            if (response.ok) {
                navigator.serviceWorker.register('/sw.js')
                    .then(registration => {
                        console.log('SW registered: ', registration);
                    })
                    .catch(registrationError => {
                        console.log('SW registration failed: ', registrationError);
                    });
            }
        }).catch(() => {
            // Service worker file doesn't exist, ignore
        });
    });
}
