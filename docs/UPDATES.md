# Aynı kullanıcı alanında güvenli güncelleme

Kullanıcı Codex Desktop'a yalnızca şunu yazar:

> Update my JOB-RADAR AI. Kayıtlı skill'in bağlı olduğu mevcut uygulama klasörünü
> bul. CV'mi, veritabanımı ve geçmişimi koru. En son kararlı GitHub Release'i
> incele; indirme ve güncelleme öncesinde onayımı iste. Yeni kurulum oluşturma.

Preferences → **Check for updates**, sabit public repository'nin GitHub
`releases/latest` metadatasını okur. CV/profil/geçmiş veya kişisel çalışma alanı
kimliği istek URL'sine, başlığa ya da gövdeye konmaz. Açılış bildirimi isteğe
bağlıdır ve varsayılan olarak kapalıdır. Ağın normal IP/User-Agent bilgisi
GitHub'a görünür. Henüz kararlı Release yoksa bunu açıkça gösterir. Önizleme
dalları kararlı dağıtım kaynağı değildir. Tarayıcı düğmesi Codex sohbetini yönetmez.

## Codex'in uygulayacağı işlem

1. Kullanıcının kayıtlı `job-radar-ai/SKILL.md` adaptöründeki **tam canonical
   skill yolunu** oku. Bunun `../../` uygulama kökü ile `.private/install-manifest.json`
   eşleşmesini doğrula. Aktif projede bulunan managed checkout da aynı şekilde
   doğrulanabilir. Birden fazla kurulum varsa doğru alanı kullanıcıya sor.
   Documents/özel klasör de geçerlidir; kullanıcı adı veya LOCALAPPDATA varsayma.
   Developer Git checkout'una bu archive updater'ı uygulama.
2. Kararlı Release notlarını, exact 40 karakter commit'i, root-level kaynak ZIP'ini,
   `release-manifest.json` içindeki dosya SHA-256'larını ve bağımsız incelenmiş ZIP
   SHA-256'sını incele. SHA'yı aynı değiştirilmiş ZIP'in içinden türetip güvenilir
   sayma. Release notundaki rastgele komutları çalıştırma. Oturum/credential dosyası
   okuma veya kopyalama.
3. Exact sürüm, kaynak, SHA, mevcut hedef alan ve yedek kapsamını gösterip kullanıcı
   onayı al. Aynı sürüm için tekrar onay isteme. **Close workspace** ile panoyu
   kapat; devam eden AI işlemine zorla müdahale etme.
4. Yalnızca public reviewed updater koduyla, mevcut özel Python kullanılarak
   ayrı bir staging alanına indir/doğrula. `scripts/update-workspace.py download`
   exact `https://github.com/eRR2/JOB-RADAR-AI/releases/download/vX.Y.Z/*.zip`
   ve önceden incelenmiş SHA ister; `--approved` sadece verilen onaydan sonra.
   Redirect yalnızca GitHub'ın HTTPS release asset sunucusuna izinlidir; özel
   ağ, auth, proxy veya ret sonrası tekrar yoktur. `stage --archive ... --destination ...
   --sha256 ... --commit ... --tag ...` path/link/özel dosya/boyut/inventory ve her
   dosyanın hash'ini doğrular. İndirilmiş script'i remote pipe/eval ile çalıştırma.
5. `apply --package <reviewed staging> --workspace <aynı kayıtlı alan>
   --commit <exact SHA> --approved` çalıştır. Çalışan alanın tüm lock'ları,
   eski managed code hash'leri ve yerel dosya çakışmaları kontrol edilir.
   Staging dosyaları exact commit/tag manifest'iyle yeniden karşılaştırılır;
   incelemeden sonra değişmiş dosya veya eksik manifest varsa kopyalama başlamaz.
   `.private/updates/backup-*` altında eski kod, CV, SQLite, raporlar ve diğer
   kariyer state'i yedeklenir. Byte hash'leri ile SQLite integrity, schema ve
   bütün tablo satırlarının hash'leri doğrulanır. Runtime/AI scratch/verification
   dosyaları yerinde kalır; provider login dışarıdan okunmaz/değiştirilmez.
6. Code replacement journal ile kaydedilir, launch gate önce atomik değiştirilir.
   Kopyalama hatasında eski kod geri alınır. Process/PC kapanırsa journal kalır:
   skill launcher yarım paketi başlatmayı reddeder. Reviewed staging updater'dan
   `recover --workspace <aynı alan> --approved` eski kodu geri alır. Yedek bozuksa
   veya kullanıcı state'i sonradan değişmişse dur; eski DB'yi otomatik üzerine yazma.
7. Aynı root ve aynı SQLite/port ile kayıtlı launcher'ı tekrar çalıştır. `/api/health`
   workspace kimliği/skill mode, private backup proof, schema/table/CV hash'leri,
   ilan/feedback/application sayıları ve görünür browser state'i karşılaştır.
   Bu sürüm DB schema 2'yi korur; migration gerektirmez. Gelecek sürüm migration
   yaparsa eski satır/CV/geri bildirimlerin korunması ayrıca doğrulanmalıdır.

Skill association, existing provider login, private runtime ve seçili uygulama
alanı değişmez. İlk kurulum helper'ı artık mevcut managed code'u değiştirmeyi
reddeder; güvenli updater kullanılmalıdır. Kullanıcıya terminal komutu verilmez;
bu işlemleri Codex yetkileri içinde yapar. Yalnızca indirilen skill uygulamanın
tamamı değildir; canonical app klasörünü değiştirmek yeni user DB yaratır.

## İlk stable Release öncesinde

Bu Phase 3 bir preview'dır. Yayın/tag için sahibinin **ayrı açık onayı** gerekir.
Onaydan sonra release scope ve notlarını incele, `version.json` stable version
commit'ini test et, privacy/history kontrollerini çalıştır. `scripts/build-release.py`
exact reviewed commit'ten yerel root-level ZIP + dosya manifest'i + SHA-256
hazırlar; tag/publish yapmaz. Preview'ı stable asset'e dönüştürmeyi reddeder.
Exact tag/commit/ZIP/SHA kaynakları release notlarında yer almalıdır.
İlk stable yayından sonra gerçek ikinci Windows PC'de aynı özel Documents
alanıyla download → backup → update → browser reopen smoke testi tamamlanmalı.
