// Summernote 0.8.20 동영상 창: 유튜브 주소를 에디터가 인식하는 형태로 바꿔 줌
// (youtu.be/ID?si=..., watch?v=ID&list=..., shorts/ID, live/ID 를 인식하지 못하고 아무것도 넣지 않는 문제)
(function () {
    'use strict';

    // 유튜브 주소면 https://www.youtube.com/watch?v=ID[&t=초] 로, 아니면 그대로 반환
    function normalizeYoutube(value) {
        var url;
        try {
            url = new URL(value.trim());
        } catch (e) {
            return value;
        }
        var host = url.hostname.replace(/^(www|m|music)\./, '');
        var id = null;
        if (host === 'youtu.be') {
            id = url.pathname.split('/')[1];
        } else if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
            var parts = url.pathname.split('/');
            if (parts[1] === 'watch') {
                id = url.searchParams.get('v');
            } else if (['shorts', 'live', 'embed', 'v'].indexOf(parts[1]) !== -1) {
                id = parts[2];
            }
        }
        if (!id || !/^[\w-]{11}$/.test(id)) {
            return value;
        }
        var result = 'https://www.youtube.com/watch?v=' + id;
        var t = url.searchParams.get('t') || url.searchParams.get('start');
        if (t && /^\d+s?$/.test(t)) {
            result += '&t=' + parseInt(t, 10);
        }
        return result;
    }

    function fix(input) {
        var normalized = normalizeYoutube(input.value);
        if (normalized !== input.value) {
            input.value = normalized;
        }
    }

    // 동영상 창의 주소 입력칸 (.note-video-url) 에 붙여넣기/입력 시 변환
    ['input', 'change', 'paste'].forEach(function (type) {
        document.addEventListener(type, function (e) {
            var input = e.target;
            if (!input.classList || !input.classList.contains('note-video-url')) {
                return;
            }
            // paste 는 이벤트 시점에 값이 아직 안 바뀌었으므로 다음 틱에 처리
            if (type === 'paste') {
                setTimeout(function () { fix(input); }, 0);
            } else {
                fix(input);
            }
        }, true);
    });

    window.normalizeYoutube = normalizeYoutube;  // 테스트용
})();
