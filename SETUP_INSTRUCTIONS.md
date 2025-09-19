# 🚀 Advanced GitHub Profile Setup Guide

## Quick Start

To deploy this stunning profile to your GitHub:

1. **Create Your Profile Repository**
   - Repository name MUST be: `ChiR24` (your GitHub username)
   - Make it public
   - Initialize with this README

2. **Enable GitHub Actions**
   - Go to Settings → Actions → General
   - Enable "Read and write permissions"
   - Allow GitHub Actions to create and approve pull requests

3. **Push The Code**
   ```bash
   git init
   git add .
   git commit -m "✨ Initial stunning profile setup"
   git remote add origin https://github.com/ChiR24/ChiR24.git
   git push -u origin main
   ```

4. **Trigger Workflows**
   - Go to Actions tab in your repository
   - Manually run the workflows to generate initial content

## 🎨 Features Included

### Dynamic Animations
- **Typing SVG Header**: Animated typing effect with multiple lines
- **Waving Banner**: Gradient animated banner with twinkling effects
- **3D Contribution Graph**: Interactive 3D visualization of your contributions
- **Activity Graph**: Real-time GitHub activity visualization
- **Tech Stack Icons**: Beautiful animated tech badges

### Advanced Metrics
- **GitHub Stats**: Detailed statistics with custom themes
- **Language Analysis**: Most used languages with visual representation
- **Contribution Streak**: Track your daily contribution streak
- **Trophy Display**: GitHub achievements and trophies
- **Code Habits**: Coding patterns and habits analysis
- **Skyline View**: 3D skyline of your contributions

### Interactive Elements
- **Collapsible Sections**: Organized content sections
- **Dev Quotes**: Random developer quotes
- **Joke Generator**: Programming jokes that refresh
- **Social Links**: Professional social media badges

## ⚙️ Configuration

### Customize Your Information

Edit the following in `README.md`:

1. **Personal Details**
   - Update the name in typing animation
   - Modify the JavaScript object with your details
   - Add your social media links

2. **Tech Stack**
   - Add/remove technology badges
   - Customize the categories
   - Update skill levels

3. **Color Themes**
   - Banner gradient colors: `customColorList=6,12,20`
   - Stats theme: `theme=tokyonight`
   - Activity graph colors: Modify hex codes

### GitHub Actions Workflows

#### 1. **metrics.yml** - Main Metrics Generator
- Runs every 6 hours
- Generates 3D contributions
- Creates detailed metrics
- Updates automatically

#### 2. **header.yml** - Header Animations
- Daily updates at 12:00 UTC
- Activity graph generation
- WakaTime integration (optional)

### Optional Integrations

#### WakaTime Setup
1. Sign up at [WakaTime](https://wakatime.com)
2. Get your API key
3. Add as GitHub Secret: `WAKATIME_API_KEY`
4. Install WakaTime plugin in your IDE

#### Spotify Recently Played (Optional)
1. Create a Spotify App
2. Add credentials as secrets
3. Uncomment Spotify section in README

## 🎯 Customization Tips

### Change Animation Speeds
```html
<!-- Typing SVG - Adjust duration and pause -->
&duration=3000&pause=1000
```

### Modify Graph Colors
```yaml
# In metrics.yml
backgroundColor: "#0d1117"  # Dark background
strongColor: "#6366f1"      # Primary color
radarColor: "#f85d7f"       # Accent color
```

### Add Custom Sections
```markdown
## 🎮 My Hobbies
- Gaming 🎮
- Photography 📸
- Travel ✈️
```

## 🐛 Troubleshooting

### Workflows Not Running?
- Check Actions tab for errors
- Ensure proper permissions in Settings
- Verify GITHUB_TOKEN is available

### Images Not Loading?
- Wait for workflows to complete
- Check if actions generated output branch
- Verify image URLs are correct

### Stats Not Updating?
- Manual trigger from Actions tab
- Check API rate limits
- Verify username is correct

## 📚 Resources

### Documentation
- [GitHub Profile README Guide](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-profile/customizing-your-profile/managing-your-profile-readme)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Metrics Plugin Documentation](https://github.com/lowlighter/metrics)

### Inspiration
- [Awesome GitHub Profiles](https://github.com/abhisheknaiidu/awesome-github-profile-readme)
- [Profile README Generator](https://rahuldkjain.github.io/gh-profile-readme-generator/)
- [GitHub Profile Views Counter](https://github.com/antonkomarev/github-profile-views-counter)

### Tools Used
- [Readme Typing SVG](https://readme-typing-svg.demolab.com/)
- [Capsule Render](https://github.com/kyechan99/capsule-render)
- [GitHub Readme Stats](https://github.com/anuraghazra/github-readme-stats)
- [GitHub Profile Trophy](https://github.com/ryo-ma/github-profile-trophy)
- [Shields.io](https://shields.io/)

## 🤝 Contributing

Feel free to fork this repository and customize it for your own profile!

## 📄 License

This project is open source and available under the MIT License.

---

<div align="center">
  Made with ❤️ for the GitHub community
</div>
