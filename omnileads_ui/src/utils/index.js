function getTrustedTargetOrigin () {
    try {
        return window.parent.location.origin;
    } catch {
        if (document.referrer) {
            return new URL(document.referrer).origin;
        }
    }
    return window.location.origin;
}

function isTrustedOrigin (origin) {
    const allowed = new Set([window.location.origin, getTrustedTargetOrigin()]);
    return allowed.has(origin);
}

export function resetStoreDataByAction ({ action, data }) {
    if (window.parent === window) {
        return;
    }
    window.parent.postMessage({ action, data }, getTrustedTargetOrigin());
}

export function listenerStoreDataByAction (action, callback) {
    window.parent.addEventListener('message', (event) => {
        if (!isTrustedOrigin(event.origin)) {
            return;
        }
        if (event.source !== window) {
            return;
        }
        if (event.data.action === action) {
            callback(event.data.data);
        }
    });
}

export function removeInPlace (array, item) {
    var foundIndex, fromIndex;

    // Look for the item (the item can have multiple indices)
    fromIndex = array.length - 1;
    foundIndex = array.lastIndexOf(item, fromIndex);

    while (foundIndex !== -1) {
        // Remove the item (in place)
        array.splice(foundIndex, 1);

        // Bookkeeping
        fromIndex = foundIndex - 1;
        foundIndex = array.lastIndexOf(item, fromIndex);
    }

    // Return the modified array
    return array;
}
