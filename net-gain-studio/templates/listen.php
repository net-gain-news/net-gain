<?php
/**
 * Template for the invitation landing page (see includes/class-listen-page.php). Wording comes from the page's
 * "Landing page text" box; the newest episode, recent headlines and anchor are pulled live.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$ngl_page_id = (int) get_queried_object_id();
$ngl_copy    = Net_Gain_Listen_Page::copy( $ngl_page_id );
$ngl_t       = function ( $key ) use ( $ngl_copy ) {
	return Net_Gain_Listen_Page::text( $ngl_copy, $key );
};
$ngl_r       = function ( $key ) use ( $ngl_copy ) {
	return Net_Gain_Listen_Page::rich( $ngl_copy, $key );
};
$ngl_show    = function_exists( 'ng_current_show_slug' ) ? (string) ng_current_show_slug() : '';
$ngl_eps     = Net_Gain_Listen_Page::recent_episodes( $ngl_show, 4 );
$ngl_latest  = $ngl_eps ? $ngl_eps[0] : null;
$ngl_show_pid = ( $ngl_show && function_exists( 'ng_show_id' ) ) ? (int) ng_show_id( $ngl_show ) : 0;
$ngl_cap_id   = $ngl_show_pid ? (string) get_post_meta( $ngl_show_pid, 'ng_captivate_show_id', true ) : '';
$ngl_player   = ( $ngl_latest && $ngl_cap_id && function_exists( 'ng_episode_captivate_embed_url' ) ) ? ng_episode_captivate_embed_url( $ngl_latest->ID, $ngl_cap_id ) : '';
$ngl_anchor  = ( $ngl_show && function_exists( 'ng_show_primary_anchor' ) ) ? ng_show_primary_anchor( $ngl_show ) : null;
$ngl_apps    = array(   // field holding the link's name => where it goes
	'app_apple'   => 'https://podcasts.apple.com/us/podcast/net-gain-edtech/id6821241606',
	'app_spotify' => 'https://open.spotify.com/show/4gtuU4Ox1mwAKuVINfXDjT',
	'app_other'   => 'https://net-gain-edtech.captivate.fm/listen',
	'app_rss'     => 'https://feeds.captivate.fm/netgain-edtech/',
);

get_header();
?>

<main class="ngl">

	<section class="ngl-hero">
		<div class="ngl-wrap ngl-hero-grid">
			<div class="ngl-hero-copy">
				<?php if ( '' !== trim( $ngl_copy['eyebrow'] ) ) : ?>
					<p class="ngl-eyebrow mono"><?php echo $ngl_t( 'eyebrow' ); ?></p>
				<?php endif; ?>
				<h1 class="arch ngl-h1"><?php echo $ngl_t( 'headline' ); ?></h1>
				<p class="ngl-lede"><?php echo $ngl_t( 'lede' ); ?></p>
			</div>

			<div class="ngl-card ngl-signup" id="ngl-signup">
				<?php if ( '' !== trim( $ngl_copy['card_kicker'] ) ) : ?>
					<p class="ngl-kicker mono"><?php echo $ngl_t( 'card_kicker' ); ?></p>
				<?php endif; ?>
				<?php echo Net_Gain_Listen_Page::form_html( $ngl_copy, 'top' ); // phpcs:ignore WordPress.Security.EscapeOutput -- built from escaped parts ?>
				<?php if ( $ngl_latest && '' !== trim( $ngl_copy['listen_first'] ) ) : ?>
					<p class="ngl-first"><a href="#listen"><?php echo $ngl_t( 'listen_first' ); ?> <span aria-hidden="true">&darr;</span></a></p>
				<?php endif; ?>
			</div>
		</div>
	</section>

	<?php if ( $ngl_latest ) : ?>
		<section class="ngl-sect" id="listen">
			<div class="ngl-wrap">
				<h2 class="arch ngl-h2"><?php echo $ngl_t( 'listen_heading' ); ?></h2>
				<div class="ngl-listen">
					<div class="ngl-art">
						<?php echo function_exists( 'ng_episode_thumb_img' ) ? ng_episode_thumb_img( $ngl_latest->ID ) : ''; // phpcs:ignore WordPress.Security.EscapeOutput -- escaped in the helper ?>
						<?php /* Only the length tag is drawn over the picture, not the play disc: the graphic is deliberately not a click target (the player below is). */ ?>
						<?php $ngl_len = function_exists( 'ng_episode_length_label' ) ? ng_episode_length_label( $ngl_latest->ID ) : ''; ?>
						<?php if ( '' !== $ngl_len ) : ?>
							<span class="ng-len" aria-label="Length <?php echo esc_attr( $ngl_len ); ?>"><?php echo esc_html( $ngl_len ); ?></span>
						<?php endif; ?>
					</div>
					<div class="ngl-listen-text">
						<p class="ngl-meta mono"><span class="ngl-chip">Latest</span><span><?php echo esc_html( get_the_date( 'F j, Y', $ngl_latest ) ); ?></span></p>
						<h3 class="arch ngl-ep-title"><?php echo esc_html( Net_Gain_Listen_Page::k12( get_the_title( $ngl_latest ) ) ); ?></h3>
						<?php $ngl_summary = trim( wp_strip_all_tags( get_the_excerpt( $ngl_latest ) ) ); ?>
						<?php if ( '' !== $ngl_summary ) : ?>
							<p class="ngl-summary"><?php echo esc_html( Net_Gain_Listen_Page::k12( $ngl_summary ) ); ?></p>
						<?php endif; ?>
						<?php if ( $ngl_player ) : ?>
							<?php /* Same player and crop as the episode page: the iframe is pulled up inside a clipping wrapper to hide Captivate's own title row. */ ?>
							<div class="ngl-player">
								<iframe src="<?php echo esc_url( $ngl_player ); ?>" title="Episode player" frameborder="no" scrolling="no" allow="clipboard-write" seamless loading="lazy"></iframe>
							</div>
						<?php endif; ?>
						<?php if ( '' !== trim( $ngl_copy['sponsor'] ) ) : ?>
							<p class="ngl-sponsor"><a class="ngl-sponsor-logo" href="https://www.edsby.com/" target="_blank" rel="sponsored noopener" aria-label="Edsby"><?php echo function_exists( 'ng_edsby_logo_img' ) ? ng_edsby_logo_img() : ''; // phpcs:ignore WordPress.Security.EscapeOutput -- escaped in the helper ?></a><span><?php echo $ngl_r( 'sponsor' ); ?></span></p>
						<?php endif; ?>
					</div>
				</div>
			</div>
		</section>
	<?php endif; ?>

	<section class="ngl-sect ngl-sect-alt">
		<div class="ngl-wrap">
			<h2 class="arch ngl-h2"><?php echo $ngl_t( 'benefits_heading' ); ?></h2>
			<div class="ngl-three">
				<?php foreach ( array( 'b1', 'b2', 'b3' ) as $ngl_b ) : ?>
					<div class="ngl-box">
						<h3 class="arch"><?php echo $ngl_t( $ngl_b . '_title' ); ?></h3>
						<p><?php echo $ngl_t( $ngl_b . '_text' ); ?></p>
					</div>
				<?php endforeach; ?>
			</div>
			<?php if ( count( $ngl_eps ) > 0 && '' !== trim( $ngl_copy['recent_heading'] ) ) : ?>
				<div class="ngl-recent">
					<p class="mono ngl-kicker"><?php echo $ngl_t( 'recent_heading' ); ?></p>
					<ul>
						<?php foreach ( array_slice( $ngl_eps, 0, 3 ) as $ngl_ep ) : ?>
							<li><?php echo esc_html( Net_Gain_Listen_Page::k12( get_the_title( $ngl_ep ) ) ); ?></li>
						<?php endforeach; ?>
					</ul>
				</div>
			<?php endif; ?>
		</div>
	</section>

	<section class="ngl-sect">
		<div class="ngl-wrap ngl-who">
			<?php if ( $ngl_anchor && function_exists( 'ng_anchor_photo_html' ) ) : ?>
				<div class="ngl-who-photo"><?php echo ng_anchor_photo_html( $ngl_anchor, 132, 38 ); // phpcs:ignore WordPress.Security.EscapeOutput -- escaped in the helper ?></div>
			<?php endif; ?>
			<div class="ngl-who-text">
				<h2 class="arch ngl-h2"><?php echo $ngl_t( 'who_heading' ); ?></h2>
				<?php if ( $ngl_anchor ) : ?>
					<p class="ngl-name"><strong><?php echo esc_html( $ngl_anchor['name'] ); ?></strong><?php echo ! empty( $ngl_anchor['title'] ) ? ' &middot; ' . esc_html( $ngl_anchor['title'] ) : ''; ?></p>
				<?php endif; ?>
				<p><?php echo $ngl_r( 'who_text' ); ?></p>
			</div>
		</div>
	</section>

	<?php if ( '' !== trim( $ngl_copy['why_text'] ) ) : ?>
		<section class="ngl-sect ngl-sect-alt">
			<div class="ngl-wrap">
				<div class="ngl-why">
					<h2 class="arch"><?php echo $ngl_t( 'why_heading' ); ?></h2>
					<p><?php echo $ngl_r( 'why_text' ); ?></p>
				</div>
			</div>
		</section>
	<?php endif; ?>

	<section class="ngl-hero ngl-bottom">
		<div class="ngl-wrap ngl-bottom-grid">
			<h2 class="arch ngl-h1 ngl-bottom-h"><?php echo $ngl_t( 'bottom_heading' ); ?></h2>
			<div class="ngl-card ngl-signup" id="ngl-signup-bottom">
				<?php echo Net_Gain_Listen_Page::form_html( $ngl_copy, 'bottom' ); // phpcs:ignore WordPress.Security.EscapeOutput -- built from escaped parts ?>
			</div>
		</div>
	</section>

	<?php if ( '' !== trim( $ngl_copy['apps_heading'] ) ) : ?>
		<section class="ngl-sect ngl-apps">
			<div class="ngl-wrap">
				<p class="mono ngl-kicker"><?php echo $ngl_t( 'apps_heading' ); ?></p>
				<div class="ngl-apps-row">
					<?php foreach ( $ngl_apps as $ngl_key => $ngl_url ) : ?>
						<a href="<?php echo esc_url( $ngl_url ); ?>" target="_blank" rel="noopener" class="mono ng-platform-link"><?php echo $ngl_t( $ngl_key ); ?></a>
					<?php endforeach; ?>
				</div>
			</div>
		</section>
	<?php endif; ?>

</main>

<div class="ngl-bar" id="ngl-bar" aria-hidden="true">
	<span class="ngl-bar-text"><?php echo $ngl_t( 'bar_text' ); ?></span>
	<button type="button" class="ngl-bar-btn" tabindex="-1"><?php echo $ngl_t( 'bar_button' ); ?> <span aria-hidden="true">&rarr;</span></button>
</div>

<?php get_footer(); ?>
