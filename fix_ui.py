import sys

path = 'src/lib/components/chat/MessageInput.svelte'
with open(path, 'r') as f:
    lines = f.readlines()

# Add imports
for i, line in enumerate(lines):
    if "import PlusAlt from '../icons/PlusAlt.svelte';" in line:
        lines[i] = line + "import { Plus, ArrowUp, Square, Globe } from 'lucide-svelte';\n"
        break

# Add icons and logic
for i, line in enumerate(lines):
    if "let showTools = false;" in line:
        lines[i] = line + """
    const CAMERA_ICON = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 4C10.8908 4 9.92091 4.60141 9.40069 5.50073C9.22194 5.80972 8.89205 6 8.53508 6H7.8C6.94342 6 6.36113 6.00078 5.91104 6.03755C5.47262 6.07337 5.24842 6.1383 5.09202 6.21799C4.7157 6.40973 4.40973 6.71569 4.21799 7.09202C4.1383 7.24842 4.07337 7.47262 4.03755 7.91104C4.00078 8.36113 4 8.94342 4 9.8V15.2C4 16.0566 4.00078 16.6389 4.03755 17.089C4.07337 17.5274 4.1383 17.7516 4.21799 17.908C4.40973 18.2843 4.7157 18.5903 5.09202 18.782C5.24842 18.8617 5.47262 18.9266 5.91104 18.9624C6.36113 18.9992 6.94342 19 7.8 19H16.2C17.0566 19 17.6389 18.9992 18.089 18.9624C18.5274 18.9266 18.7516 18.8617 18.908 18.782C19.2843 18.5903 19.5903 18.2843 19.782 17.908C19.8617 17.7516 19.9266 17.5274 19.9624 17.089C19.9992 16.6389 20 16.0566 20 15.2V9.8C20 8.94342 19.9992 8.36113 19.9624 7.91104C19.9266 7.47262 19.8617 7.24842 19.782 7.09202C19.5903 6.71569 19.2843 6.40973 18.908 6.21799C18.7516 6.1383 18.5274 6.07337 18.089 6.03755C17.6389 6.00078 17.0566 6 16.2 6H15.4648C15.1079 6 14.778 5.80972 14.5992 5.50073C14.079 4.60141 13.1091 4 12 4ZM7.99973 4C8.91084 2.78702 10.363 2 12 2C13.6369 2 15.0891 2.78702 16.0002 4L16.2413 4C17.0463 3.99999 17.7106 3.99998 18.2518 4.04419C18.8139 4.09012 19.3306 4.18868 19.816 4.43597C20.5686 4.81947 21.1805 5.43139 21.564 6.18404C21.8113 6.66937 21.9099 7.18608 21.9558 7.74817C22 8.28936 22 8.95372 22 9.75868V15.2413C22 16.0463 22 16.7106 21.9558 17.2518C21.9099 17.8139 21.8113 18.3306 21.564 18.816C21.1805 19.5686 20.5686 20.1805 19.816 20.564C19.3306 20.8113 18.8139 20.9099 18.2518 20.9558C17.7106 21 17.0463 21 16.2413 21H7.75868C6.95372 21 6.28936 21 5.74817 20.9558C5.18608 20.9099 4.66937 20.8113 4.18404 20.564C3.43139 20.1805 2.81947 19.5686 2.43597 18.816C2.18868 18.3306 2.09012 17.8139 2.04419 17.2518C1.99998 16.7106 1.99999 16.0463 2 15.2413V9.7587C1.99999 8.95373 1.99998 8.28937 2.04419 7.74817C2.09012 7.18608 2.18868 6.66937 2.43597 6.18404C2.81947 5.43139 3.43139 4.81947 4.18404 4.43597C4.66937 4.18868 5.18608 4.09012 5.74817 4.04419C6.28937 3.99998 6.95373 3.99999 7.7587 4L7.99973 4ZM12 10C10.7573 10 9.74995 11.0074 9.74995 12.25C9.74995 13.4926 10.7573 14.5 12 14.5C13.2426 14.5 14.25 13.4926 14.25 12.25C14.25 11.0074 13.2426 10 12 10ZM7.74995 12.25C7.74995 9.90279 9.65274 8 12 8C14.3472 8 16.25 9.90279 16.25 12.25C16.25 14.5972 14.3472 16.5 12 16.5C9.65274 16.5 7.74995 14.5972 7.74995 12.25Z" />
  </svg>`

    const PHOTO_ICON = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path d="M8.7587 3H15.2413C16.0463 2.99999 16.7106 2.99998 17.2518 3.04419C17.8139 3.09012 18.3306 3.18868 18.816 3.43597C19.5686 3.81947 20.1805 4.43139 20.564 5.18404C20.8113 5.66937 20.9099 6.18608 20.9558 6.74817C21 7.28936 21 7.95372 21 8.75868V15.2413C21 16.0463 21 16.7106 20.9558 17.2518C20.9099 17.8139 20.8113 18.3306 20.564 18.816C20.1805 19.5686 19.5686 20.1805 18.816 20.564C18.3306 20.8113 17.8139 20.9099 17.2518 20.9558C16.7106 21 16.0463 21 15.2413 21H8.75868C7.95372 21 7.28936 21 6.74817 20.9558C6.18608 20.9099 5.66937 20.8113 5.18404 20.564C4.43139 20.1805 3.81947 19.5686 3.43597 18.816C3.18868 18.3306 3.09012 17.8139 3.04419 17.2518C2.99998 16.7106 2.99999 16.0463 3 15.2413V8.7587C2.99999 7.95373 2.99998 7.28937 3.04419 6.74817C3.09012 6.18608 3.18868 5.66937 3.43597 5.18404C3.81947 4.43139 4.43139 3.81947 5.18404 3.43597C5.66937 3.18868 6.18608 3.09012 6.74817 3.04419C7.28937 2.99998 7.95373 2.99999 8.7587 3ZM6.91104 5.03755C6.47262 5.07337 6.24842 5.1383 6.09202 5.21799C5.7157 5.40973 5.40973 5.7157 5.21799 6.09202C5.1383 6.24842 5.07337 6.47262 5.03755 6.91104C5.00078 7.36113 5 7.94342 5 8.8V13.5857L5.87868 12.707C7.05026 11.5355 8.94975 11.5355 10.1213 12.7071L16.4073 18.9931C16.6681 18.9878 16.8913 18.9786 17.089 18.9624C17.5274 18.9266 17.7516 18.8617 17.908 18.782C18.2843 18.5903 18.5903 18.2843 18.782 17.908C18.8617 17.7516 18.9266 17.5274 18.9624 17.089C18.9992 16.6389 19 16.0566 19 15.2V8.8C19 7.94342 18.9992 7.36113 18.9624 6.91104C18.9266 6.47262 18.8617 6.24842 18.782 6.09202C18.5903 5.7157 18.2843 5.40973 17.908 5.21799C17.7516 5.1383 17.5274 5.07337 17.089 5.03755C16.6389 5.00078 16.0566 5 15.2 5H8.8C7.94342 5 7.36113 5.00078 6.91104 5.03755ZM13.5858 19L8.70711 14.1213C8.31658 13.7307 7.68342 13.7307 7.2929 14.1213L5.00694 16.4072C5.01219 16.668 5.0214 16.8912 5.03755 17.089C5.07337 17.5274 5.1383 17.7516 5.21799 17.908C5.40973 18.2843 5.7157 18.5903 6.09202 18.782C6.24842 18.8617 6.47262 18.9266 6.91104 18.9624C7.36113 18.9992 7.94342 19 8.8 19H13.5858ZM14.5 8.5C13.9477 8.5 13.5 8.94772 13.5 9.5C13.5 10.0523 13.9477 10.5 14.5 10.5C15.0523 10.5 15.5 10.0523 15.5 9.5C15.5 8.94772 15.0523 8.5 14.5 8.5ZM11.5 9.5C11.5 7.84315 12.8431 6.5 14.5 6.5C16.1569 6.5 17.5 7.84315 17.5 9.5C17.5 11.1569 16.1569 12.5 14.5 12.5C12.8431 12.5 11.5 11.1569 11.5 9.5Z" />
  </svg>`

    const FILE_ICON = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
    <path fillRule="evenodd" d="M9 7a5 5 0 0 1 10 0v8a7 7 0 1 1-14 0V9a1 1 0 0 1 2 0v6a5 5 0 0 0 10 0V7a3 3 0 1 0-6 0v8a1 1 0 1 0 2 0V9a1 1 0 1 1 2 0v6a3 3 0 1 1-6 0V7Z" clipRule="evenodd" />
  </svg>`

    const MENU_ITEMS = [
        { icon: CAMERA_ICON, label: 'Aparat' },
        { icon: PHOTO_ICON, label: 'Zdjęcia' },
        { icon: FILE_ICON, label: 'Pliki' }
    ];

    let openPlusMenu = false;
    let cameraInputRef: HTMLInputElement | null = null;
    let photosInputRef: HTMLInputElement | null = null;

    function handlePlusPick(kind: 'camera' | 'photos' | 'files') {
        openPlusMenu = false;
        if (kind === 'camera') {
            cameraInputRef?.click();
            return;
        }
        if (kind === 'photos') {
            photosInputRef?.click();
            return;
        }
        filesInputElement?.click();
    }
"""
        break

# Update placeholder
for i, line in enumerate(lines):
    if "placeholder={placeholder ? placeholder : $i18n.t('Send a Message')}" in line:
        lines[i] = line.replace("$i18n.t('Send a Message')", "'Zapytaj o cokolwiek'")

# Replace form content
content = "".join(lines)

# This is the most complex part. I will find the container and replace everything until the end of the form.
# But we need to keep the inner content.
# I'll use a simpler method: find the container start and the send button area.

start_marker = '<div id="message-input-container"'
# We'll find the first occurrence of the start marker.
start_idx = content.find(start_marker)

# Find the submit button area to replace.
# It's usually at the end of the container.
end_marker = '</div>\n\t\t\t\t\t\t\t</div>\n\n\t\t\t\t\t\t\t{#if $config?.license_metadata?.input_footer}'
# If that doesn't work, let's find the send button specifically.
send_button_marker = '<button\n\t\t\t\t\t\t\t\t\t\tid="send-message-button"'

# Actually, I'll just do a very targeted replacement of the container and the bottom menu.
# Replacement for the container start:
container_start_old = """<div
id="message-input-container"
class="flex items-center gap-2 rounded-full border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-3 py-2 shadow-[0_0_40px_rgba(0,0,0,0.04)] dark:shadow-none"
dir={$settings?.chatDirection ?? 'auto'}
>"""
# Wait, I already replaced it in the previous step.

# Let's just write the whole thing carefully.
with open(path, 'w') as f:
    f.write(content)
