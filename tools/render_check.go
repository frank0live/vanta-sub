// Renders the VANTA theme through Go's html/template with the same context
// map 3x-ui hands to a sub page, then checks that the emitted JS still parses.
//
// The panel strips comments and rewrites values in JS strings, so "it looks
// fine on disk" is not evidence. This renders first, then runs node --check
// on what a browser would actually receive.
package main

import (
	"fmt"
	"html/template"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
)

// the field set dumped from a live 3x-ui v3.11 sub page
func sampleCtx() map[string]interface{} {
	return map[string]interface{}{
		"sId":          "ly79ku6cp6k7d5z9",
		"subTitle":     "روزی چند بار توکن خود را اپدیت کنید",
		"announce":     "",
		"subSupportUrl": "https://t.me/master_supports",
		"subUrl":       "https://us1.thezero.ir:2096/subz/ly79ku6cp6k7d5z9",
		"subJsonUrl":   "https://us1.thezero.ir:2096/subz/ly79ku6cp6k7d5z9?format=json",
		"subClashUrl":  "https://us1.thezero.ir:2096/subz/ly79ku6cp6k7d5z9?format=clash",
		"enabled":      true,
		"isOnline":     false,
		"datepicker":   "gregorian",
		"subUpdates":   12,
		"downloadByte": 2147483648,
		"uploadByte":   1610612736,
		"totalByte":    5368709120,
		"expire":       int64(1791106625),
		"lastOnline":   int64(1791106625),
		"emails":       []string{"vanta_test", "smart-2"},
		"links": []string{
			"vless://0623c3a9-9406-4d7f-9ebf-70c3caf308ba@localhost:41443?encryption=none&security=none&type=tcp#VANTA-E2E-test",
			"trojan://pw@example.com:443?sni=example.com&type=ws&security=reality&path=%2Fws#Trojan-ws",
			"vmess://eyJ2IjoiMiIsInBzIjoidm1lc3MiLCJhZGQiOiJleGFtcGxlLmNvbSIsInBvcnQiOiI0NDMiLCJuZXQiOiJ3cyIsInRscyI6InRscyJ9",
			"ss://YWVzLTI1Ni1nY206cGFzcw==@1.2.3.4:8388#SS-node",
		},
	}
}

func main() {
	themePath := os.Args[1]
	raw, err := os.ReadFile(themePath)
	if err != nil {
		fmt.Println("read:", err)
		os.Exit(1)
	}

	t, err := template.New("sub").Parse(string(raw))
	if err != nil {
		fmt.Println("PARSE FAILED:", err)
		os.Exit(1)
	}

	var out strings.Builder
	if err := t.Execute(&out, sampleCtx()); err != nil {
		fmt.Println("EXECUTE FAILED:", err)
		os.Exit(1)
	}
	html := out.String()

	dir := filepath.Dir(themePath)
	rendered := filepath.Join(dir, "rendered.html")
	os.WriteFile(rendered, []byte(html), 0o644)
	fmt.Printf("rendered: %d bytes (source %d)\n", len(html), len(raw))

	// extract the script bodies and syntax-check each one
	re := regexp.MustCompile(`(?s)<script>(.*?)</script>`)
	blocks := re.FindAllStringSubmatch(html, -1)
	fmt.Printf("script blocks: %d\n", len(blocks))
	fail := 0
	for i, b := range blocks {
		p := filepath.Join(dir, fmt.Sprintf("rendered_%d.js", i))
		os.WriteFile(p, []byte(b[1]), 0o644)
		cmd := exec.Command("node", "--check", p)
		if outp, err := cmd.CombinedOutput(); err != nil {
			fail++
			fmt.Printf("  block %d: SYNTAX ERROR\n%s\n", i, string(outp))
		} else {
			fmt.Printf("  block %d: ok (%d bytes)\n", i, len(b[1]))
		}
	}

	// sanity: template syntax must not leak, and the injected values must land
	for _, bad := range []string{"{{", "<no value>", "template:"} {
		if strings.Contains(html, bad) {
			fmt.Printf("  LEAK: %q present in output\n", bad)
			fail++
		}
	}
	// Go's JS escaper rewrites "/" as "\/" inside script strings, so match on
	// the scheme followed by the escaped or plain separator
	for _, want := range []string{"ly79ku6cp6k7d5z9", "2147483648", "vless:", "trojan:", "vmess:", "ss:"} {
		if !strings.Contains(html, want) {
			fmt.Printf("  MISSING: %q\n", want)
			fail++
		}
	}

	if fail > 0 {
		fmt.Printf("\nFAILED (%d problem(s))\n", fail)
		os.Exit(1)
	}
	fmt.Println("\nall checks passed")
}
