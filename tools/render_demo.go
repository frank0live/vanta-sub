// Renders the VANTA theme with demo data so screenshots for the README can be
// taken without exposing a real subscription token or a live panel host.
package main

import (
	"fmt"
	"html/template"
	"os"
	"strings"
)

func demoCtx() map[string]interface{} {
	return map[string]interface{}{
		"sId":           "demo0token0vanta0",
		"subTitle":      "VANTA · اشتراک من",
		"announce":      "",
		"subSupportUrl": "",
		"subUrl":        "https://panel.example.com/sub/demo0token0vanta0",
		"subJsonUrl":    "https://panel.example.com/sub/demo0token0vanta0?format=json",
		"subClashUrl":   "",
		"enabled":       true,
		"isOnline":      true,
		"datepicker":    "gregorian",
		"subUpdates":    12,
		"downloadByte":  int64(19327352832),
		"uploadByte":    int64(2147483648),
		"totalByte":     int64(85899345920),
		"expire":        int64(1795123200),
		"lastOnline":    int64(1795046400),
		"emails":        []string{"VANTA-DEMO"},
		"links": []string{
			"vless://11111111-2222-3333-4444-555555555555@de1.vanta.net:443?encryption=none&security=tls&type=ws&sni=de1.vanta.net&path=%2Fws#DE%20%C2%B7%20Frankfurt",
			"vless://11111111-2222-3333-4444-555555555555@fi1.vanta.net:443?encryption=none&security=reality&type=tcp&sni=fi1.vanta.net#FI%20%C2%B7%20Helsinki",
			"trojan://demopassword@nl1.vanta.net:443?sni=nl1.vanta.net&type=ws&security=tls&path=%2Fws#NL%20%C2%B7%20Amsterdam",
			"vless://11111111-2222-3333-4444-555555555555@tr1.vanta.net:8443?encryption=none&security=tls&type=grpc&serviceName=grpc&sni=tr1.vanta.net#TR%20%C2%B7%20Istanbul",
			"vless://11111111-2222-3333-4444-555555555555@ir1.vanta.net:2087?encryption=none&security=none&type=ws&path=%2Fws#IR%20%C2%B7%20Tehran",
			"ss://YWVzLTI1Ni1nY206ZGVtb3Bhc3M@ca1.vanta.net:8388#CA%20%C2%B7%20Toronto",
		},
	}
}

func main() {
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Println("read:", err)
		os.Exit(1)
	}
	t, err := template.New("sub").Parse(string(raw))
	if err != nil {
		fmt.Println("parse:", err)
		os.Exit(1)
	}
	var b strings.Builder
	if err := t.Execute(&b, demoCtx()); err != nil {
		fmt.Println("execute:", err)
		os.Exit(1)
	}
	out := "/tmp/vanta-demo.html"
	os.WriteFile(out, []byte(b.String()), 0o644)
	fmt.Printf("wrote %s (%d bytes)\n", out, b.Len())
}
