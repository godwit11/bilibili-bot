(() => {
    const result = [];
    const items = document.querySelectorAll('.interaction-item');
    const botName = 'Nya是妮娅啦';

    items.forEach((item, index) => {
        const userEl = item.querySelector('.interaction-item__title');
        const actionEl = item.querySelector('.interaction-item__action');
        const msgEl = item.querySelector('.interaction-item__msg, .message-text-nodes');
        const timeEl = item.querySelector('.interaction-item__time');

        const user = userEl ? userEl.innerText.trim() : '';
        const action = actionEl ? actionEl.innerText.trim() : '';
        const repliedContent = msgEl ? msgEl.innerText.trim() : '';
        const time = timeEl ? timeEl.innerText.trim() : '';
        const fullText = item.innerText || '';

        // 计算 userReply（用户实际写的回复内容）
        // 通过 DOM 元素结构判断:
        // - msgEl.innerText = 被回复的评论内容（可能带 "回复 @bot : 内容" 前缀）
        // - referenceEl.innerText = bot 的回复内容（如果存在）
        // userReply = referenceEl 存在时为空（已回复），否则是 msgEl 的内容
        const referenceEl = item.querySelector('.interaction-item__reference');
        const alreadyReplied = !!referenceEl;

        let userReply = '';
        if (action && time) {
            const actionIdx = fullText.indexOf(action);
            if (actionIdx !== -1) {
                const afterAction = fullText.substring(actionIdx + action.length);
                const timeIdx = afterAction.indexOf(time);
                if (timeIdx !== -1) {
                    let rawReply = afterAction.substring(0, timeIdx)
                        .replace(/\n+/g, ' ').replace(/[\s\xa0]+/g, ' ').trim();
                    if (repliedContent && repliedContent.includes('回复 @')) {
                        const colonIdx = repliedContent.lastIndexOf(':');
                        if (colonIdx !== -1) {
                            userReply = repliedContent.substring(colonIdx + 1).trim();
                        }
                    } else {
                        userReply = rawReply;
                    }
                }
            }
        }

        if (user && action) {
            result.push({
                user,
                action,
                content: repliedContent,
                user_reply: userReply,
                time,
                alreadyReplied,
                _fullText: fullText
            });
        }
    });
    return result;
})()
